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
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    CONF_API_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    UNIFIED_METRICS_ENDPOINT,
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
            # Single 2-day window covers today + tomorrow; the API returns
            # whatever hours have published prices.
            today_local = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
            window_end_local = today_local + timedelta(days=2)
            start_utc = dt_util.as_utc(today_local).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = dt_util.as_utc(window_end_local).strftime("%Y-%m-%dT%H:%M:%SZ")

            raw = await self._fetch_unified_data(start_utc, end_utc)
            data = self._process_unified_data(raw)

            # Dynamically adjust the next update to align with the top of the hour
            now_utc = dt_util.utcnow()
            next_hour = now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            self.update_interval = next_hour - now_utc

            await self._save_cache(data)
            return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            _LOGGER.warning("API error: %s. Loading data from cache if available.", error)
            cached = await self._load_cache()
            if cached is not None:
                return cached
            raise UpdateFailed(f"Error communicating with API: {error}") from error

    async def _fetch_unified_data(self, start_utc: str, end_utc: str) -> dict[str, Any]:
        """Fetch pricing data from the unified-metrics endpoint."""
        endpoint = UNIFIED_METRICS_ENDPOINT.format(start=start_utc, end=end_utc)
        url = f"{API_BASE_URL}/{endpoint}"

        _LOGGER.debug("Requesting unified metrics from %s", url)

        try:
            async with self._session.get(url, headers=self._headers, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                if response.status in (401, 403):
                    raise ConfigEntryAuthFailed(
                        "Authentication failed. API token may be invalid."
                    )
                _LOGGER.error("Error fetching unified metrics: %s", response.status)
                raise aiohttp.ClientError(
                    f"Error fetching unified metrics: {response.status}"
                )
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching data from Pstryk API")
            raise

    def _process_unified_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process unified-metrics response into the buy/sell structure sensors expect.

        Each frame contains ``metrics.pricing`` with both ``price_gross`` (buy)
        and ``price_prosumer_gross`` (sell) in a single object.
        """
        frames = data.get("frames", [])
        if not frames:
            _LOGGER.warning("No frames returned from unified-metrics endpoint")
            empty: dict[str, Any] = {"prices": [], "current_price": None, ATTR_IS_CHEAP: False, ATTR_IS_EXPENSIVE: False, "has_future_data": False}
            return {"buy": dict(empty), "sell": dict(empty)}

        now_utc = dt_util.utcnow()
        today = dt_util.now().date()

        buy_prices: list[dict[str, Any]] = []
        sell_prices: list[dict[str, Any]] = []
        buy_current: float | None = None
        sell_current: float | None = None
        cur_is_cheap = False
        cur_is_expensive = False
        has_future_data = False

        for frame in frames:
            pricing = frame.get("metrics", {}).get("pricing")
            if pricing is None:
                continue

            buy_val = _to_float_precise(pricing.get("price_gross"))
            sell_val = _to_float_precise(pricing.get("price_prosumer_gross"))

            start = dt_util.parse_datetime(frame["start"])
            end = dt_util.parse_datetime(frame["end"])
            if not start or not end:
                _LOGGER.warning("Invalid datetime format in unified-metrics frame")
                continue

            local_start = dt_util.as_local(start)
            timestamp = local_start.isoformat()

            frame_is_cheap = pricing.get(ATTR_IS_CHEAP, False)
            frame_is_expensive = pricing.get(ATTR_IS_EXPENSIVE, False)

            entry_base = {
                "timestamp": timestamp,
                "hour": local_start.hour,
                ATTR_IS_CHEAP: frame_is_cheap,
                ATTR_IS_EXPENSIVE: frame_is_expensive,
            }

            if buy_val is not None:
                buy_prices.append({**entry_base, "price": buy_val})
            if sell_val is not None:
                sell_prices.append({**entry_base, "price": sell_val})

            if start <= now_utc < end:
                buy_current = buy_val
                sell_current = sell_val
                cur_is_cheap = frame_is_cheap
                cur_is_expensive = frame_is_expensive

            if local_start.date() > today:
                has_future_data = True

        buy_prices.sort(key=lambda x: x["timestamp"])
        sell_prices.sort(key=lambda x: x["timestamp"])

        return {
            "buy": {
                "prices": buy_prices,
                "current_price": buy_current,
                ATTR_IS_CHEAP: cur_is_cheap,
                ATTR_IS_EXPENSIVE: cur_is_expensive,
                "has_future_data": has_future_data,
            },
            "sell": {
                "prices": sell_prices,
                "current_price": sell_current,
                ATTR_IS_CHEAP: cur_is_cheap,
                ATTR_IS_EXPENSIVE: cur_is_expensive,
                "has_future_data": has_future_data,
            },
        }