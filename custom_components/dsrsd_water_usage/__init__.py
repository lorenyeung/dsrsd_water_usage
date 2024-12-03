from .sensor import AcwdWaterUsage
from .const import DOMAIN

async def async_setup(hass, config):
    """Set up the ACWD Water Usage component."""
    return True

async def async_setup_entry(hass, config_entry):
    """Set up ACWD Water Usage from a config entry."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, "sensor")
    )
    return True

async def async_unload_entry(hass, config_entry):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    return True

