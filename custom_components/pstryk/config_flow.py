"""Config flow for Pstryk.pl integration."""
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE_URL, CONF_API_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): str,
        vol.Optional(CONF_NAME, default="Pstryk"): str,
    }
)


async def validate_api_token(hass: HomeAssistant, api_token: str) -> bool:
    """Validate the API token by making a test request."""
    session = async_get_clientsession(hass)
    headers = {"Authorization": f"Bearer {api_token}"}
    
    try:
        async with session.get(
            f"{API_BASE_URL}/pricing/", headers=headers, timeout=10
        ) as response:
            return response.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False


class PstrykConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pstryk.pl."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            valid = await validate_api_token(
                self.hass, user_input[CONF_API_TOKEN]
            )

            if valid:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )