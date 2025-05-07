"""Data update coordinator for the Pstryk.pl integration."""
import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    BUY_ENDPOINT,
    CONF_API_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SELL_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


class PstrykDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, session: aiohttp.ClientSession, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self._session = session
        self._api_token = entry.data[CONF_API_TOKEN]
        self._headers = {"Authorization": f"Bearer {self._api_token}"}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""
        try:
            data = {
                "buy": await self._fetch_buy_data(),
                "sell": await self._fetch_sell_data(),
            }
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise UpdateFailed(f"Error communicating with API: {error}") from error

    async def _fetch_buy_data(self) -> dict[str, Any]:
        """Fetch buying price data from the API."""
        now = datetime.now().astimezone()
        now_utc = now.astimezone(datetime.timezone.utc)
        start = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
        end = (now_utc + timedelta(days=2)).strftime("%Y-%m-%d")
        
        url = f"{API_BASE_URL}/{BUY_ENDPOINT.format(start=start, end=end)}"
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching buy data. API token may be invalid.")
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                else:
                    _LOGGER.error("Error fetching buy data: %s", response.status)
                    raise aiohttp.ClientError(f"Error fetching buy data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching buy data from Pstryk API")
            raise

    async def _fetch_sell_data(self) -> dict[str, Any]:
        """Fetch selling price data from the API."""
        now = datetime.now().astimezone()
        now_utc = now.astimezone(datetime.timezone.utc)
        start = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
        end = (now_utc + timedelta(days=2)).strftime("%Y-%m-%d")
        
        url = f"{API_BASE_URL}/{SELL_ENDPOINT.format(start=start, end=end)}"
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching sell data. API token may be invalid.")
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                else:
                    _LOGGER.error("Error fetching sell data: %s", response.status)
                    raise aiohttp.ClientError(f"Error fetching sell data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching sell data from Pstryk API")
            raise