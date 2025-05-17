"""Data update coordinator for the Pstryk.pl integration."""
import asyncio
import logging
import json
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
    ATTR_IS_CHEAP,
    ATTR_IS_EXPENSIVE,
)

_LOGGER = logging.getLogger(__name__)


def _to_float_precise(value: str | float | int | Decimal, ndigits: int = 3) -> float | None:
    """Convert incoming price string/number to float with Decimal for precise
    rounding.

    Returns ``None`` if conversion fails.
    """
    try:
        dec = Decimal(str(value).replace(",", ".").strip())
        quant = Decimal("1e-{0}".format(ndigits))
        dec = dec.quantize(quant, rounding=ROUND_HALF_UP)
        return float(dec)
    except (InvalidOperation, ValueError, TypeError) as err:
        _LOGGER.warning("Price conversion error: %s", err)
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
        self._cache_file = hass.config.path(f"{DOMAIN}_cache.json")

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _load_cache(self) -> dict[str, Any] | None:
        """Load cached data from disk."""
        if not os.path.exists(self._cache_file):
            return None

        def _read() -> dict[str, Any] | None:
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning("Failed to read cache: %s", err)
                return None

        return await asyncio.to_thread(_read)

    async def _save_cache(self, data: dict[str, Any]) -> None:
        """Persist data to disk."""

        def _write() -> None:
            try:
                with open(self._cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning("Failed to write cache: %s", err)

        await asyncio.to_thread(_write)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""
        try:
            # Always fetch current data
            buy_data = await self._fetch_pricing_data("buy", force_future=False)
            sell_data = await self._fetch_pricing_data("sell", force_future=False)

            # Also fetch next day data if it's available (after 14:00 UTC)
            now_utc = dt_util.utcnow()
            is_future_data_time = now_utc.hour >= 14  # Next day data available after 14:00 UTC

            if is_future_data_time:
                future_buy_data = await self._fetch_pricing_data("buy", force_future=True)
                future_sell_data = await self._fetch_pricing_data("sell", force_future=True)

                # Merge future data with current data
                if future_buy_data.get("prices") and buy_data.get("prices"):
                    buy_data["prices"].extend(future_buy_data.get("prices", []))
                    buy_data["has_future_data"] = True

                if future_sell_data.get("prices") and sell_data.get("prices"):
                    sell_data["prices"].extend(future_sell_data.get("prices", []))
                    sell_data["has_future_data"] = True

            # Dynamically adjust the next update to align with the top of the hour
            next_hour = now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            self.update_interval = next_hour - now_utc

            data = {"buy": buy_data, "sell": sell_data}
            await self._save_cache(data)
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.warning("API error: %s. Loading data from cache if available.", error)
            cached = await self._load_cache()
            if cached is not None:
                return cached
            raise UpdateFailed(f"Error communicating with API: {error}") from error

    async def _fetch_pricing_data(self, price_type: str, force_future: bool = False) -> dict[str, Any]:
        """Fetch pricing data from the API.

        If force_future is True, attempts to fetch future data for the next day.
        Future pricing data is typically available after 14:00 UTC.
        """
        today_local = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        window_end_local = today_local + timedelta(days=2)

        # If we're forcing future data (after 14:00 UTC), try to get data for tomorrow
        if force_future:
            _LOGGER.debug("Attempting to fetch future pricing data for %s", price_type)
            tomorrow_local = today_local + timedelta(days=1)
            window_end_local = tomorrow_local + timedelta(days=1)
            start_utc = dt_util.as_utc(tomorrow_local).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
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
        has_future_data = False
        
        for frame in frames:
            val = _to_float_precise(frame.get("price_gross"))
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
            frame_is_cheap = frame.get(ATTR_IS_CHEAP, False)
            frame_is_expensive = frame.get(ATTR_IS_EXPENSIVE, False)
            
            prices.append({
                "timestamp": timestamp,
                "hour": local_start.hour,
                "price": val,
                ATTR_IS_CHEAP: frame_is_cheap,
                ATTR_IS_EXPENSIVE: frame_is_expensive
            })
            
            if start <= now_utc < end:
                current_price = val
                is_cheap = frame_is_cheap
                is_expensive = frame_is_expensive
                
            # Check if we have data for future days
            if local_start.date() > dt_util.now().date():
                has_future_data = True
        
        # Sort prices by timestamp
        prices = sorted(prices, key=lambda x: x["timestamp"])
        
        return {
            "prices": prices,
            "current_price": current_price,
            ATTR_IS_CHEAP: is_cheap,
            ATTR_IS_EXPENSIVE: is_expensive,
            "has_future_data": has_future_data
        }