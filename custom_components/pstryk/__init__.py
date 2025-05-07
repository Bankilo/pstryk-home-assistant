"""The Pstryk.pl integration."""
import asyncio
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .config_flow import validate_api_token
from .const import CONF_API_TOKEN, COORDINATOR, DOMAIN
from .coordinator import PstrykDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Pstryk.pl from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    
    # Validate API token before setting up
    try:
        valid, error = await validate_api_token(hass, entry.data[CONF_API_TOKEN])
        if not valid:
            _LOGGER.error(
                "Failed to connect to Pstryk.pl API during setup: %s", error
            )
            raise ConfigEntryNotReady(
                f"Failed to connect to Pstryk.pl API: {error}"
            )
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.error("Error connecting to Pstryk.pl API: %s", err)
        raise ConfigEntryNotReady(
            f"Error connecting to Pstryk.pl API: {err}"
        ) from err
    
    coordinator = PstrykDataUpdateCoordinator(hass, session, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Error during initial data refresh: %s", err)
        raise ConfigEntryNotReady(
            f"Error during initial data refresh: {err}"
        ) from err

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok