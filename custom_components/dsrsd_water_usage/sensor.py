"""Platform for DSRSD Water Usage integration."""
import logging
import requests
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfVolume
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt as dt_util
from zoneinfo import ZoneInfo

from .const import DOMAIN

# Set the scan interval to 3 hours
SCAN_INTERVAL = timedelta(hours=3)

_LOGGER = logging.getLogger(__name__)

# Constants
BASE_URL = "https://dsrsd.aquahawk.us"
DEFAULT_API_PREFIX = BASE_URL + "/"
USAGES_API_PREFIX = BASE_URL + "/"
BILLING_API_PREFIX = BASE_URL + "/"

class DSRSDWaterUsage(Entity):
    """Representation of an DSRSD Water Usage."""

    def __init__(self, hass, username, password):
        """Initialize the sensor."""
        self._state = None
        self.hass = hass
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.account_number = None
        self.billing_details = {}
        self.dates = []
        self.time_series_data = []  # List to store time series data
        _LOGGER.info("DSRSD Water Usage initialized")

    @property
    def should_poll(self):
        """Return True as updates are needed via polling."""
        return True

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"DSRSD_{self.username}"

    @property
    def name(self):
        return 'DSRSD Water Usage'

    @property
    def state(self):
        return self._state

    @property
    def state_class(self):
        return SensorStateClass.TOTAL

    @property
    def unit_of_measurement(self):
        return UnitOfVolume.GALLONS

    @property
    def device_class(self):
        return SensorDeviceClass.WATER

    @property
    def icon(self):
        return "mdi:water"

    def get_water_usage(self, num_days=30):
 
        """Fetch and combine water usage data for a specified number of past days."""
        login_success = self.login()
        
        if not login_success:
            _LOGGER.error("Failed to log in for water usage data")
            return None

        self.account_number = self.bind_multi_meter()
        self.billing_details = self.get_billing_data()
        if not self.account_number:
            _LOGGER.error("Failed to bind meter for water usage data")
            return None
        all_records = []
        today = datetime.today()
        localized_end_datetime = today.replace(tzinfo=ZoneInfo("America/Los_Angeles"),microsecond=0)
        end_iso_format = localized_end_datetime.isoformat()
        
        start = today - timedelta(days=num_days)
        localized_start_datetime = start.replace(tzinfo=ZoneInfo("America/Los_Angeles"),microsecond=0)
        start_iso_format = localized_start_datetime.isoformat()

        for day in range(num_days, 0, -1):
            date_str = self.get_date_x_days_ago(day)
            self.dates.append(date_str)

        water_usage_response = self.call_load_water_usage_api(start_iso_format, end_iso_format, self.account_number)
        if water_usage_response:
            records = water_usage_response.get('timeseries', [])
            for record in records:
                usage_date_str = record.get('startTime')

                waterUseActual = record.get('waterUseActual')
                usage_value = waterUseActual.get('gallons')
                # datetime_str = f"{usage_date_str}"
                # datetime_obj = datetime.strptime(datetime_str, "%B %d, %Y %I:%M %p")
                # datetime_iso_str = datetime_obj.isoformat()
                all_records.append((usage_date_str, usage_value))
        else:
            _LOGGER.error(f"Failed to fetch water usage data for {date_str}")

        self.logout()
        return all_records

    def update_statistics(self, new_data: list[tuple[str, float]]):
        stats_meta = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name="DSRSD Water Usage",
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:{self.account_number}_usage",
            unit_of_measurement=UnitOfVolume.GALLONS,
        )

        usage_sum = 0
        stats_data = []
        for datetime_str, usage in new_data:
            localized_timestamp = datetime.fromisoformat(datetime_str).replace(
                tzinfo=dt_util.DEFAULT_TIME_ZONE
            )
            usage_sum += usage
            stats_data.append(StatisticData(start=localized_timestamp, state=usage, sum=usage_sum))

        async_add_external_statistics(self.hass, stats_meta, stats_data)

    async def async_update(self):
        try:
            _LOGGER.debug("Getting Time Series Data")
            new_data = await self.hass.async_add_executor_job(self.get_water_usage, 7)  # Fetch data for 7 days
            _LOGGER.debug("Getting Time Series Data failed get maybe: %s", new_data)
            if False:
                self.update_statistics(new_data)

                self.time_series_data.extend(new_data)

                # Calculate the total gallons by summing up the usage values
                total_gallons = sum(value for _, value in self.time_series_data)
                
                # Update the state with the total gallons
                self._state = total_gallons
                _LOGGER.debug("Get current billing details: %s", self.billing_details)
                projected = "0"
                current = "0"
                if self.billing_details != None:
                    projected = self.billing_details.get("projected", {}).get("billing period", {}).get("total")
                    current = self.billing_details.get("current", {}).get("billing period", {}).get("total")

                self._attr_extra_state_attributes = {
                    "time_series": self.time_series_data,
                    "username": self.username,
                    "account_number": self.account_number,
                    "connect.sid": self.session.cookies.get("connect.sid"),
                    "start_date": self.dates[0],
                    "end_date": self.dates[-1],
                    "projected_bill": projected,
                    "current_bill": current,
                }
        except Exception as e:
            _LOGGER.error("Error updating water usage data: %s", e)

    def login(self):
        response = self.session.get(BASE_URL)
        login_url = DEFAULT_API_PREFIX + "login"
        headers = self.get_api_headers()
        data = {
            "username": self.username,
            "password": self.password,
        }

        _LOGGER.debug("Sending login POST request")
        login_response_json = self.make_api_request(login_url, headers, data)
        if login_response_json:
            login_success = login_response_json.get('response') == 200
            _LOGGER.info(f"Login {'succeeded' if login_success else 'failed'}")
            return login_success
        _LOGGER.warning("Login failed: No response data")
        return False

    def logout(self):
        response = self.session.get(DEFAULT_API_PREFIX + 'logout')
        # Check if the logout was successful (optional)
        if response.status_code == 200:
            _LOGGER.debug("Logout successful")
        else:
            _LOGGER.warning("Logout failed. Status code:", response.status_code)

    def bind_multi_meter(self):
        api_url = USAGES_API_PREFIX + "accounts"
        headers = self.get_api_headers()
        response_json = self.make_get_api_request(api_url, headers, {}, True)
        if response_json:
            meters = response_json.get("accounts", [{}])
            # Iterate until we find a meter where 'Advanced Meter Infrastructure' == TRUE
            for meter in meters:
                if meter.get("IsAMI"):
                    return meter.get("_id", "")
            # Otherwise, return the first meter
            return meters[0].get("_id", "")
            

        _LOGGER.warning("Meter details failed: No response data")
        return None

    def get_billing_data(self):
        api_url = BILLING_API_PREFIX + "accounts"
        headers = self.get_api_headers()

        response_json = self.make_get_api_request(api_url, headers, {}, True)
        if response_json:
            attributes = response_json.get("accounts", [])
            for attribute in attributes:
                if attribute.get("metricAggregates"):
                    bills = attribute.get("metricAggregates")
                    return bills.get("billAmount")
        _LOGGER.warning("Billing details failed: No response data")
        return None

    def call_load_water_usage_api(self, start, end, account_number):
        api_url = USAGES_API_PREFIX + "timeseries"
        headers = self.get_api_headers()
        params = {
            "startTime": start,
            "endTime": end,
            "interval": "1 day",
            "districtName": "dsrsd",
            "accountNumber": account_number,
            "extraStartTime": "true",
            "extraEndTime": "true",
            "metrics": {"waterUse":"true","waterUseReading":"true","temperature":"false","rainfall":"false"}
        }

        return self.make_get_api_request(api_url, headers, params, True)

    def make_api_request(self, url, headers, data, extract_json=True):
        _LOGGER.debug(f"Sending request to URL: {url}")

        response = self.session.post(url, headers=headers, data=json.dumps(data))
        _LOGGER.debug(f"Response status: {response.status_code}")
        _LOGGER.debug(f"Response data: {response.text}")
        if url.endswith("login"):
            _LOGGER.debug(f"This is a login, trying notes API")
            return self.make_get_api_request(DEFAULT_API_PREFIX+ "notes", headers, {}, False)
        else: 
            try:
                response_json =  response.json()
                if response_json:
                    if extract_json:
                        return self.extract_json_from_response(response_json, 'd')
                    else:
                        return response_json.get('d', {})
                return None
            except json.JSONDecodeError as e:
                _LOGGER.error(f"Failed to decode JSON from response: {e}")
                return None

    def make_get_api_request(self, url, headers, params, extract_json=True):
        _LOGGER.debug(f"Sending request to URL: {url}")

        response = self.session.get(url, headers=headers, params=params)
        _LOGGER.debug(f"Response status: {response.status_code}")
        _LOGGER.debug(f"Response data: {response.text}")
        if extract_json:
            try:
                response_json =  response.json()
                return response_json
            except json.JSONDecodeError as e:
                _LOGGER.error(f"Failed to decode JSON from response: {e}")
                return None
        else:
            return {'response': response.status_code, 'data': response.text}
                

    def extract_json_from_response(self, response_json, key):
        json_str = response_json.get(key, '{}')
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}

    def get_api_headers(self):
        return {
            'Content-Type': 'application/json',
            'Accept': "application/json",
            'Cookie': f'connect.sid={self.session.cookies.get("connect.sid")}'
        }

    def get_date_x_days_ago(self, days):
        date_x_days_ago = datetime.now() - timedelta(days)
        return date_x_days_ago.strftime("%B %d, %Y")

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the DSRSD Water Usage from a config entry."""
    username = config_entry.data["username"]
    password = config_entry.data["password"]

    sensor = DSRSDWaterUsage(hass, username, password)
    async_add_entities([sensor], True)
