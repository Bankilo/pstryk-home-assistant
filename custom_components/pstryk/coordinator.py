"""Data update coordinator for the Pstryk.pl integration."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    BUY_ENDPOINT,
    CONF_API_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SELL_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


def convert_price(value):
    """Convert price string to float."""
    try:
        return round(float(str(value).replace(",", ".").strip()), 2)
    except (ValueError, TypeError) as e:
        _LOGGER.warning("Price conversion error: %s", e)
        return None


class PstrykDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, session: aiohttp.ClientSession, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self._session = session
        self._api_token = entry.data[CONF_API_TOKEN]
        self._headers = {"Authorization": f"{self._api_token}", "Accept": "application/json"}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""
        try:
            buy_data = await self._fetch_pricing_data("buy")
            sell_data = await self._fetch_pricing_data("sell")
            
            return {
                "buy": buy_data,
                "sell": sell_data,
            }
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise UpdateFailed(f"Error communicating with API: {error}") from error

    async def _fetch_pricing_data(self, price_type: str) -> dict[str, Any]:
        """Fetch pricing data from the API."""
        today_local = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        window_end_local = today_local + timedelta(days=2)
        start_utc = dt_util.as_utc(today_local).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = dt_util.as_utc(window_end_local).strftime("%Y-%m-%dT%H:%M:%SZ")

        endpoint_tpl = BUY_ENDPOINT if price_type == "buy" else SELL_ENDPOINT
        endpoint = endpoint_tpl.format(start=start_utc, end=end_utc)
        url = f"{API_BASE_URL}/{endpoint}"
        
        _LOGGER.debug("Requesting %s data from %s", price_type, url)
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._process_pricing_data(data, price_type)
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching %s data. API token may be invalid.", price_type)
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                else:
                    _LOGGER.error("Error fetching %s data: %s", price_type, response.status)
                    raise aiohttp.ClientError(f"Error fetching {price_type} data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching %s data from Pstryk API", price_type)
            raise

    def _process_pricing_data(self, data: dict, price_type: str) -> dict:
        """Process the raw API data into a format usable by the sensor."""
        frames = data.get("frames", [])
        if not frames:
            _LOGGER.warning("No frames returned for %s prices", price_type)
            return {"prices": []}
            
        now_utc = dt_util.utcnow()
        prices = []
        current_price = None
        is_cheap = False
        is_expensive = False
        
        for frame in frames:
            val = convert_price(frame.get("price_gross"))
            if val is None:
                continue
                
            start = dt_util.parse_datetime(frame["start"])
            end = dt_util.parse_datetime(frame["end"])
            
            # Validate dates
            if not start or not end:
                _LOGGER.warning("Invalid datetime format in frames for %s", price_type)
                continue
                
            local_start = dt_util.as_local(start)
            timestamp = local_start.isoformat()
            
            # Get is_cheap and is_expensive flags
            frame_is_cheap = frame.get("is_cheap", False)
            frame_is_expensive = frame.get("is_expensive", False)
            
            prices.append({
                "timestamp": timestamp,
                "hour": local_start.hour,
                "price": val,
                "is_cheap": frame_is_cheap,
                "is_expensive": frame_is_expensive
            })
            
            if start <= now_utc < end:
                current_price = val
                is_cheap = frame_is_cheap
                is_expensive = frame_is_expensive
        
        # Sort prices by timestamp
        prices = sorted(prices, key=lambda x: x["timestamp"])
        
        return {
            "prices": prices,
            "current_price": current_price,
            "is_cheap": is_cheap,
            "is_expensive": is_expensive
        }