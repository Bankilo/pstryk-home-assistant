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
    CONF_METER_IP,
    DEFAULT_SCAN_INTERVAL,
    METER_SCAN_INTERVAL,
    DOMAIN,
    SELL_ENDPOINT,
    ENERGY_COST_ENDPOINT,
    ENERGY_USAGE_ENDPOINT,
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


def _get_meter_energy_value(meter_data: dict, sensor_type: str) -> float | None:
    """Extract energy-related sensor value from meter data for sensor id=0."""
    if not meter_data or "multiSensor" not in meter_data:
        return None
    
    sensors = meter_data["multiSensor"].get("sensors", [])
    for sensor in sensors:
        if sensor.get("id") == 0 and sensor.get("type") == sensor_type:
            value = sensor.get("value")
            if value is not None:
                return float(value)
    return None


def _get_meter_total_current(meter_data: dict) -> float | None:
    """Calculate total current by summing values from sensors with id=1,2,3 and type=current."""
    if not meter_data or "multiSensor" not in meter_data:
        return None
    
    sensors = meter_data["multiSensor"].get("sensors", [])
    total_current = 0
    found_sensors = 0
    
    for sensor_id in [1, 2, 3]:
        for sensor in sensors:
            if sensor.get("id") == sensor_id and sensor.get("type") == "current":
                value = sensor.get("value")
                if value is not None:
                    total_current += float(value)
                    found_sensors += 1
                break
    
    # Return total only if at least one sensor was found
    return total_current if found_sensors > 0 else None


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
        self._meter_ip = entry.data.get(CONF_METER_IP)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        
        # Setup separate timer for meter data if meter is configured
        if self._meter_ip:
            self._setup_meter_timer()

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
            
            # Fetch energy cost data for previous hour
            energy_cost_data = await self._fetch_energy_cost_data()
            
            # Fetch energy usage data for previous hour
            energy_usage_data = await self._fetch_energy_usage_data()
            
            # Fetch energy cost and usage data for previous day
            energy_cost_yesterday = await self._fetch_energy_cost_yesterday()
            energy_usage_yesterday = await self._fetch_energy_usage_yesterday()
            
            # Fetch energy cost and usage data for previous month
            energy_cost_previous_month = await self._fetch_energy_cost_previous_month()
            energy_usage_previous_month = await self._fetch_energy_usage_previous_month()
            
            # Fetch energy cost and usage data for current day
            energy_cost_today = await self._fetch_energy_cost_today()
            energy_usage_today = await self._fetch_energy_usage_today()
            
            # Fetch energy cost and usage data for current month
            energy_cost_current_month = await self._fetch_energy_cost_current_month()
            energy_usage_current_month = await self._fetch_energy_usage_current_month()
            
            # Fetch meter state data if meter is configured
            meter_state_data = None
            if self._meter_ip:
                meter_state_data = await self._fetch_meter_state_data()

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

            data = {
                "buy": buy_data, 
                "sell": sell_data, 
                "energy_cost": energy_cost_data, 
                "energy_usage": energy_usage_data,
                "energy_cost_yesterday": energy_cost_yesterday,
                "energy_usage_yesterday": energy_usage_yesterday,
                "energy_cost_previous_month": energy_cost_previous_month,
                "energy_usage_previous_month": energy_usage_previous_month,
                "energy_cost_today": energy_cost_today,
                "energy_usage_today": energy_usage_today,
                "energy_cost_current_month": energy_cost_current_month,
                "energy_usage_current_month": energy_usage_current_month
            }
            
            # Add meter state data if available
            if meter_state_data is not None:
                data["meter_state"] = meter_state_data
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

    async def _fetch_energy_cost_data(self) -> dict[str, Any]:
        """Fetch energy cost data for the previous full hour."""
        now_utc = dt_util.utcnow()
        
        # Get previous full hour window
        current_hour_start = now_utc.replace(minute=0, second=0, microsecond=0)
        previous_hour_start = current_hour_start - timedelta(hours=1)
        previous_hour_end = current_hour_start

        start_utc = previous_hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = previous_hour_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        endpoint = ENERGY_COST_ENDPOINT.format(start=start_utc, end=end_utc)
        url = f"{API_BASE_URL}/{endpoint}"
        
        _LOGGER.debug("Requesting energy cost data from %s", url)
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._process_energy_cost_data(data)
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching energy cost data. API token may be invalid.")
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                elif response.status == 404:
                    _LOGGER.warning("Energy cost data not found for previous hour - meter may not have usage data yet")
                    return {"previous_hour_cost": None, "total_cost": None}
                else:
                    _LOGGER.error("Error fetching energy cost data: %s", response.status)
                    response_text = await response.text()
                    raise aiohttp.ClientError(f"Error fetching energy cost data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching energy cost data from Pstryk API")
            raise

    def _process_energy_cost_data(self, data: dict) -> dict[str, Any]:
        """Process the raw energy cost API data."""
        frames = data.get("frames", [])
        fae_total_cost = data.get("fae_total_cost")  # This is the actual total cost field
        total_energy_balance_value = data.get("total_energy_balance_value")
        
        if not frames:
            _LOGGER.warning("No energy cost frames returned")
            total_cost_value = None
            if fae_total_cost is not None:
                total_cost_value = _to_float_precise(fae_total_cost)
            return {"previous_hour_cost": None, "total_cost": total_cost_value}
        
        # Get the cost for the single frame (previous hour)
        frame = frames[0] if frames else {}
        
        # The main cost appears to be in 'energy_balance_value' field
        raw_frame_cost = frame.get("energy_balance_value")
        
        frame_cost = None
        if raw_frame_cost is not None:
            frame_cost = _to_float_precise(raw_frame_cost)
        
        total_cost_value = None
        if fae_total_cost is not None:
            total_cost_value = _to_float_precise(fae_total_cost)
        
        # Extract detailed cost breakdown from frame
        cost_breakdown = {}
        cost_fields = ['fae_cost', 'var_dist_cost_net', 'fix_dist_cost_net', 
                      'energy_cost_net', 'service_cost_net', 'excise', 'vat', 
                      'energy_sold_value', 'energy_balance_value']
        
        for field in cost_fields:
            if field in frame:
                cost_breakdown[field] = _to_float_precise(frame[field])
        
        return {
            "previous_hour_cost": frame_cost,
            "total_cost": total_cost_value,
            "frame_details": {
                "start": frame.get("start"),
                "end": frame.get("end"),
                "cost": frame_cost,
                "is_live": frame.get("is_live", False),
                "cost_breakdown": cost_breakdown
            }
        }

    async def _fetch_energy_usage_data(self) -> dict[str, Any]:
        """Fetch energy usage data for the previous full hour."""
        now_utc = dt_util.utcnow()
        
        # Get previous full hour window
        current_hour_start = now_utc.replace(minute=0, second=0, microsecond=0)
        previous_hour_start = current_hour_start - timedelta(hours=1)
        previous_hour_end = current_hour_start

        start_utc = previous_hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = previous_hour_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        endpoint = ENERGY_USAGE_ENDPOINT.format(start=start_utc, end=end_utc)
        url = f"{API_BASE_URL}/{endpoint}"
        
        _LOGGER.debug("Requesting energy usage data from %s", url)
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._process_energy_usage_data(data)
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching energy usage data. API token may be invalid.")
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                elif response.status == 404:
                    _LOGGER.warning("Energy usage data not found for previous hour - meter may not have usage data yet")
                    return {"previous_hour_usage": None, "previous_hour_production": None, "total_usage": None, "total_production": None}
                else:
                    _LOGGER.error("Error fetching energy usage data: %s", response.status)
                    response_text = await response.text()
                    raise aiohttp.ClientError(f"Error fetching energy usage data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching energy usage data from Pstryk API")
            raise

    def _process_energy_usage_data(self, data: dict) -> dict[str, Any]:
        """Process the raw energy usage API data."""
        frames = data.get("frames", [])
        fae_total_usage = data.get("fae_total_usage")  # Total usage
        rae_total = data.get("rae_total")  # Total production
        
        if not frames:
            _LOGGER.warning("No energy usage frames returned")
            total_usage_value = None
            total_production_value = None
            if fae_total_usage is not None:
                total_usage_value = _to_float_precise(fae_total_usage)
            if rae_total is not None:
                total_production_value = _to_float_precise(rae_total)
            return {
                "previous_hour_usage": None, 
                "previous_hour_production": None,
                "total_usage": total_usage_value,
                "total_production": total_production_value
            }
        
        # Get the usage for the single frame (previous hour)
        frame = frames[0] if frames else {}
        
        # Extract usage and production values
        raw_fae_usage = frame.get("fae_usage")  # Energy consumed
        raw_rae = frame.get("rae")  # Energy produced
        
        frame_usage = None
        if raw_fae_usage is not None:
            frame_usage = _to_float_precise(raw_fae_usage)
        
        frame_production = None
        if raw_rae is not None:
            frame_production = _to_float_precise(raw_rae)
        
        total_usage_value = None
        if fae_total_usage is not None:
            total_usage_value = _to_float_precise(fae_total_usage)
        
        total_production_value = None
        if rae_total is not None:
            total_production_value = _to_float_precise(rae_total)
        
        # Extract detailed usage breakdown from frame
        usage_breakdown = {}
        usage_fields = ['fae_usage', 'rae', 'energy_balance']
        
        for field in usage_fields:
            if field in frame:
                usage_breakdown[field] = _to_float_precise(frame[field])
        
        return {
            "previous_hour_usage": frame_usage,
            "previous_hour_production": frame_production,
            "total_usage": total_usage_value,
            "total_production": total_production_value,
            "frame_details": {
                "start": frame.get("start"),
                "end": frame.get("end"),
                "usage": frame_usage,
                "production": frame_production,
                "is_live": frame.get("is_live", False),
                "usage_breakdown": usage_breakdown
            }
        }

    async def _fetch_meter_state_data(self) -> dict[str, Any] | None:
        """Fetch current state data from Pstryk meter.
        
        Returns processed meter state data or None if unavailable.
        """
        if not self._meter_ip:
            return None
            
        # Ensure we have http:// prefix
        if not self._meter_ip.startswith(('http://', 'https://')):
            meter_url = f"http://{self._meter_ip}"
        else:
            meter_url = self._meter_ip
        
        if not meter_url.endswith('/'):
            meter_url += '/'
        
        try:
            async with self._session.get(f"{meter_url}state", timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug("Successfully fetched meter state data from %s", self._meter_ip)
                    return data
                    
                else:
                    _LOGGER.warning(
                        "Failed to fetch meter state data: HTTP %s", response.status
                    )
                    return None
                    
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching meter state data from %s", self._meter_ip)
            return None
        except aiohttp.ClientError as err:
            _LOGGER.error("Client error when fetching meter state data: %s", err)
            return None
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error when fetching meter state data: %s", err)
            return None

    def _setup_meter_timer(self) -> None:
        """Setup recurring timer for meter data updates."""
        async def _update_meter_data(now) -> None:
            """Update meter data independently from API data."""
            try:
                meter_data = await self._fetch_meter_state_data()
                if meter_data is not None:
                    # Update only the meter_state part of coordinator data
                    if self.data is None:
                        self.data = {}
                    self.data["meter_state"] = meter_data
                    # Notify listeners of the update
                    self.async_update_listeners()
            except Exception as err:
                _LOGGER.error("Error updating meter data: %s", err)
        
        # Schedule recurring meter updates
        from homeassistant.helpers.event import async_track_time_interval
        async_track_time_interval(
            self.hass, _update_meter_data, METER_SCAN_INTERVAL
        )

    async def _fetch_energy_cost_period(self, start_datetime, end_datetime, period_name: str) -> dict[str, Any]:
        """Fetch energy cost data for a specific period."""
        start_utc = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

        endpoint = ENERGY_COST_ENDPOINT.format(start=start_utc, end=end_utc)
        url = f"{API_BASE_URL}/{endpoint}"
        
        _LOGGER.debug("Requesting %s energy cost data from %s", period_name, url)
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._process_energy_cost_period_data(data, period_name)
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching %s energy cost data", period_name)
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                elif response.status == 404:
                    _LOGGER.warning("Energy cost data not found for %s", period_name)
                    return {f"{period_name}_cost": None, f"{period_name}_total_cost": None}
                else:
                    _LOGGER.error("Error fetching %s energy cost data: %s", period_name, response.status)
                    raise aiohttp.ClientError(f"Error fetching {period_name} energy cost data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching %s energy cost data from Pstryk API", period_name)
            raise

    async def _fetch_energy_usage_period(self, start_datetime, end_datetime, period_name: str) -> dict[str, Any]:
        """Fetch energy usage data for a specific period."""
        start_utc = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

        endpoint = ENERGY_USAGE_ENDPOINT.format(start=start_utc, end=end_utc)
        url = f"{API_BASE_URL}/{endpoint}"
        
        _LOGGER.debug("Requesting %s energy usage data from %s", period_name, url)
        
        try:
            async with self._session.get(url, headers=self._headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._process_energy_usage_period_data(data, period_name)
                elif response.status == 401 or response.status == 403:
                    _LOGGER.error("Authentication failed when fetching %s energy usage data", period_name)
                    raise aiohttp.ClientError("Authentication failed, API token may be invalid")
                elif response.status == 404:
                    _LOGGER.warning("Energy usage data not found for %s", period_name)
                    return {f"{period_name}_usage": None, f"{period_name}_production": None}
                else:
                    _LOGGER.error("Error fetching %s energy usage data: %s", period_name, response.status)
                    raise aiohttp.ClientError(f"Error fetching {period_name} energy usage data: {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout when fetching %s energy usage data from Pstryk API", period_name)
            raise

    async def _fetch_energy_cost_yesterday(self) -> dict[str, Any]:
        """Fetch energy cost data for the previous day."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start_local = today_start_local - timedelta(days=1)
        yesterday_start_utc = dt_util.as_utc(yesterday_start_local)
        today_start_utc = dt_util.as_utc(today_start_local)

        return await self._fetch_energy_cost_period(yesterday_start_utc, today_start_utc, "yesterday")

    async def _fetch_energy_usage_yesterday(self) -> dict[str, Any]:
        """Fetch energy usage data for the previous day."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start_local = today_start_local - timedelta(days=1)
        yesterday_start_utc = dt_util.as_utc(yesterday_start_local)
        today_start_utc = dt_util.as_utc(today_start_local)

        return await self._fetch_energy_usage_period(yesterday_start_utc, today_start_utc, "yesterday")

    async def _fetch_energy_cost_previous_month(self) -> dict[str, Any]:
        """Fetch energy cost data for the previous month."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        first_day_this_month_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if first_day_this_month_local.month == 1:
            last_month_start_local = first_day_this_month_local.replace(year=first_day_this_month_local.year - 1, month=12)
        else:
            last_month_start_local = first_day_this_month_local.replace(month=first_day_this_month_local.month - 1)
        
        last_month_start_utc = dt_util.as_utc(last_month_start_local)
        previous_month_end_utc = dt_util.as_utc(first_day_this_month_local)

        return await self._fetch_energy_cost_period(last_month_start_utc, previous_month_end_utc, "previous_month")

    async def _fetch_energy_usage_previous_month(self) -> dict[str, Any]:
        """Fetch energy usage data for the previous month."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        first_day_this_month_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if first_day_this_month_local.month == 1:
            last_month_start_local = first_day_this_month_local.replace(year=first_day_this_month_local.year - 1, month=12)
        else:
            last_month_start_local = first_day_this_month_local.replace(month=first_day_this_month_local.month - 1)
        
        last_month_start_utc = dt_util.as_utc(last_month_start_local)
        previous_month_end_utc = dt_util.as_utc(first_day_this_month_local)

        return await self._fetch_energy_usage_period(last_month_start_utc, previous_month_end_utc, "previous_month")

    async def _fetch_energy_cost_today(self) -> dict[str, Any]:
        """Fetch energy cost data for the current day."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = dt_util.as_utc(today_start_local)
        now_utc = dt_util.utcnow()

        return await self._fetch_energy_cost_period(today_start_utc, now_utc, "today")

    async def _fetch_energy_usage_today(self) -> dict[str, Any]:
        """Fetch energy usage data for the current day."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = dt_util.as_utc(today_start_local)
        now_utc = dt_util.utcnow()

        return await self._fetch_energy_usage_period(today_start_utc, now_utc, "today")

    async def _fetch_energy_cost_current_month(self) -> dict[str, Any]:
        """Fetch energy cost data for the current month."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        current_month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_start_utc = dt_util.as_utc(current_month_start_local)
        now_utc = dt_util.utcnow()

        return await self._fetch_energy_cost_period(current_month_start_utc, now_utc, "current_month")

    async def _fetch_energy_usage_current_month(self) -> dict[str, Any]:
        """Fetch energy usage data for the current month."""
        # Use local time first, then convert to UTC to ensure 00:00 local time = correct UTC
        now_local = dt_util.now()
        current_month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_start_utc = dt_util.as_utc(current_month_start_local)
        now_utc = dt_util.utcnow()

        return await self._fetch_energy_usage_period(current_month_start_utc, now_utc, "current_month")

    def _process_energy_cost_period_data(self, data: dict, period: str) -> dict[str, Any]:
        """Process energy cost data for a specific period (yesterday or previous_month)."""
        frames = data.get("frames", [])
        fae_total_cost = data.get("fae_total_cost")
        
        if not frames:
            _LOGGER.warning("No energy cost frames returned for %s", period)
            total_cost_value = None
            if fae_total_cost is not None:
                total_cost_value = _to_float_precise(fae_total_cost)
            return {f"{period}_cost": None, f"{period}_total_cost": total_cost_value}
        
        # Sum up all frame costs for the period
        total_period_cost = 0
        sell_value_total = 0
        
        for frame in frames:
            frame_cost = frame.get("energy_balance_value")
            if frame_cost is not None:
                frame_cost_float = _to_float_precise(frame_cost)
                if frame_cost_float is not None:
                    total_period_cost += frame_cost_float
            
            # Also sum up sell values
            frame_sell = frame.get("energy_sold_value")
            if frame_sell is not None:
                frame_sell_float = _to_float_precise(frame_sell)
                if frame_sell_float is not None:
                    sell_value_total += frame_sell_float
        
        total_cost_value = None
        if fae_total_cost is not None:
            total_cost_value = _to_float_precise(fae_total_cost)
        
        return {
            f"{period}_cost": total_period_cost if total_period_cost != 0 else None,
            f"{period}_sell_value": sell_value_total if sell_value_total != 0 else None,
            f"{period}_total_cost": total_cost_value,
            f"{period}_frame_count": len(frames),
            "period_details": {
                "start": frames[0].get("start") if frames else None,
                "end": frames[-1].get("end") if frames else None,
                "frames": len(frames)
            }
        }

    def _process_energy_usage_period_data(self, data: dict, period: str) -> dict[str, Any]:
        """Process energy usage data for a specific period (yesterday or previous_month)."""
        frames = data.get("frames", [])
        fae_total_usage = data.get("fae_total_usage")
        rae_total = data.get("rae_total")
        
        if not frames:
            _LOGGER.warning("No energy usage frames returned for %s", period)
            total_usage_value = None
            total_production_value = None
            if fae_total_usage is not None:
                total_usage_value = _to_float_precise(fae_total_usage)
            if rae_total is not None:
                total_production_value = _to_float_precise(rae_total)
            return {
                f"{period}_usage": None,
                f"{period}_production": None,
                f"{period}_total_usage": total_usage_value,
                f"{period}_total_production": total_production_value
            }
        
        # Sum up all frame usage/production for the period
        total_period_usage = 0
        total_period_production = 0
        
        for frame in frames:
            frame_usage = frame.get("fae_usage")
            if frame_usage is not None:
                frame_usage_float = _to_float_precise(frame_usage)
                if frame_usage_float is not None:
                    total_period_usage += frame_usage_float
            
            frame_production = frame.get("rae")
            if frame_production is not None:
                frame_production_float = _to_float_precise(frame_production)
                if frame_production_float is not None:
                    total_period_production += frame_production_float
        
        total_usage_value = None
        if fae_total_usage is not None:
            total_usage_value = _to_float_precise(fae_total_usage)
        
        total_production_value = None
        if rae_total is not None:
            total_production_value = _to_float_precise(rae_total)
        
        return {
            f"{period}_usage": total_period_usage if total_period_usage != 0 else None,
            f"{period}_production": total_period_production if total_period_production != 0 else None,
            f"{period}_total_usage": total_usage_value,
            f"{period}_total_production": total_production_value,
            f"{period}_frame_count": len(frames),
            "period_details": {
                "start": frames[0].get("start") if frames else None,
                "end": frames[-1].get("end") if frames else None,
                "frames": len(frames)
            }
        }