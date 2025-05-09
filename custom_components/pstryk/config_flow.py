"""Config flow for Pstryk.pl integration."""

import asyncio
import hashlib
import logging
from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL, CONF_API_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): str,
        vol.Optional(CONF_NAME, default="Pstryk"): str,
    }
)


async def validate_api_token(hass: HomeAssistant, api_token: str) -> tuple[bool, str]:
    """Validate the API token by making a test request.
    
    Returns a tuple of (is_valid, error_message).
    If is_valid is True, error_message will be an empty string.
    """
    session = async_get_clientsession(hass)
    headers = {"Authorization": f"{api_token}", "Accept": "application/json"}
    now = dt_util.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    start_utc = today.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = tomorrow.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    try:
        async with session.get(
            f"{API_BASE_URL}/pricing/?resolution=hour&window_start={start_utc}&window_end={end_utc}", 
            headers=headers, 
            timeout=30
        ) as response:
            if response.status == 200:
                # Verify we can parse the response
                try:
                    data = await response.json()
                    if "frames" in data:
                        return True, ""
                    else:
                        _LOGGER.error("API response missing 'frames' field")
                        return False, "invalid_response"
                except Exception as err:
                    _LOGGER.error("Error parsing API response: %s", err)
                    return False, "invalid_response"
            elif response.status == 401 or response.status == 403:
                return False, "invalid_auth"
            else:
                _LOGGER.error("Unexpected response from API: %s", response.status)
                return False, "cannot_connect"
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout when connecting to Pstryk API")
        return False, "timeout_error"
    except aiohttp.ClientError as err:
        _LOGGER.error("Client error when connecting to Pstryk API: %s", err)
        return False, "cannot_connect"
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error when validating Pstryk API token: %s", err)
        return False, "unknown"


class PstrykConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pstryk.pl."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Use a stable hash of the API token as unique_id so the same
            # account cannot be configured twice, regardless of the chosen
            # friendly name.
            unique = hashlib.sha256(user_input[CONF_API_TOKEN].encode()).hexdigest()
            await self.async_set_unique_id(unique)
            self._abort_if_unique_id_configured()
            
            # Validate API token
            valid, error = await validate_api_token(
                self.hass, user_input[CONF_API_TOKEN]
            )

            if valid:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )
            else:
                errors["base"] = error
                _LOGGER.warning(
                    "Failed to connect to Pstryk API with provided token. Error: %s", error
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )