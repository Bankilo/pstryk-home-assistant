"""Diagnostics support for Pstryk.pl integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import PstrykConfigEntry
from .const import CONF_API_TOKEN

TO_REDACT = [CONF_API_TOKEN]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PstrykConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinator_data": entry.runtime_data.data,
    }
