import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN

class DsrsdWaterUsageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DSRSD Water Usage."""

    async def async_step_user(self, user_input=None):
        """Manage the configurations from the user interface."""
        errors = {}

        if user_input is not None:
            # Validate user input here and process the configuration
            return self.async_create_entry(title="DSRSD Water Usage", data=user_input)

        data_schema = vol.Schema({
            vol.Required("username", description={"suggested_value": ""}): str,
            vol.Required("password", description={"suggested_value": ""}): str,
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors,
            description_placeholders={
                "description": "Enter your DSRSD credentials to connect"
            }
        )


