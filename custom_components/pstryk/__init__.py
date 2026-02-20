"""The Pstryk.pl integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import PstrykDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type PstrykConfigEntry = ConfigEntry[PstrykDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PstrykConfigEntry) -> bool:
    """Set up Pstryk.pl from a config entry."""
    session = async_get_clientsession(hass)

    coordinator = PstrykDataUpdateCoordinator(hass, session, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Error during initial data refresh: %s", err)
        raise ConfigEntryNotReady(
            f"Error during initial data refresh: {err}"
        ) from err

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PstrykConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
