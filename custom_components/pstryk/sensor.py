"""Sensor platform for Pstryk.pl integration."""
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CHEAP_HOURS,
    ATTR_CURRENT_PRICE,
    ATTR_EXPENSIVE_HOURS,
    ATTR_IS_CHEAP,
    ATTR_IS_EXPENSIVE,
    ATTR_NEXT_HOUR_PRICE,
    ATTR_PRICES,
    ATTR_PRICES_FUTURE,
    ATTR_PRICES_TODAY,
    ATTR_PRICES_TOMORROW,
    ATTR_PREVIOUS_HOUR_ENERGY_COST,
    CONF_METER_IP,
    COORDINATOR,
    DOMAIN,
)
from .coordinator import PstrykDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Pstryk.pl sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    # Add sensors
    entities = [
        PstrykBuyPriceSensor(coordinator),
        PstrykSellPriceSensor(coordinator),
        # "Next hour" price sensors expose the price for the upcoming hour
        # as the main state. They rely on the same coordinator data and do not
        # require any extra API calls.
        PstrykBuyNextHourPriceSensor(coordinator),
        PstrykSellNextHourPriceSensor(coordinator),
        # Energy cost sensors for previous full hour
        PstrykBuyEnergyCostSensor(coordinator),
        PstrykSellEnergyCostSensor(coordinator),
        # Energy usage sensors for previous full hour
        PstrykBuyEnergyUsageSensor(coordinator),
        PstrykSellEnergyProductionSensor(coordinator),
    ]
    
    # Add meter sensors if meter is configured
    meter_ip = entry.data.get(CONF_METER_IP)
    if meter_ip:
        from .meter_sensors import PstrykEnergyPowerSensor, PstrykCurrentSensor
        entities.extend([
            PstrykEnergyPowerSensor(coordinator),
            PstrykCurrentSensor(coordinator),
        ])

    async_add_entities(entities)


class PstrykBaseSensor(CoordinatorEntity, SensorEntity):
    """Base Pstryk sensor entity."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN/kWh"

    def __init__(self, coordinator: PstrykDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, "pstryk_energy_prices")},
            "name": "Pstryk Energy Prices",
            "manufacturer": "Pstryk.pl",
            "model": "API",
            "sw_version": "1.0",
        }


# -----------------------------------------------------------------------------
# Generic hourly price sensor
# -----------------------------------------------------------------------------


class _PstrykPriceSensor(PstrykBaseSensor):
    """Shared implementation for buy/sell price sensors."""

    # Must be set by subclass ("buy" | "sell")
    _price_key: str = "buy"

    # Subclass may override icon/name/unique_id as usual

    # -------------------- Helpers --------------------
    def _price_branch(self) -> Optional[dict]:
        """Return the nested dict for the configured price type."""
        if not self.coordinator.data or self._price_key not in self.coordinator.data:
            return None
        return self.coordinator.data[self._price_key]

    # -------------------- Home Assistant properties --------------------
    @property
    def native_value(self) -> Optional[float]:
        """Current price for the ongoing hour."""
        branch = self._price_branch()
        if branch is None:
            return None
        value = branch.get("current_price")
        # Ensure HA receives a float (Decimal would work too but float is the
        # de-facto standard for sensors).
        return float(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Organise price frames into today / tomorrow / future buckets and
        expose helper attributes shared by both buy & sell sensors."""

        branch = self._price_branch()
        if branch is None:
            return {}

        try:
            now = dt_util.now()
            prices = branch.get("prices", [])

            today_prices: list[tuple[str, float]] = []
            tomorrow_prices: list[tuple[str, float]] = []
            future_prices: list[dict] = []
            next_hour_price: Optional[float] = None

            next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

            for p in prices:
                ts_str = p.get("timestamp")
                if not ts_str:
                    continue

                p_dt = dt_util.parse_datetime(ts_str)
                if p_dt is None:
                    continue

                p_local = dt_util.as_local(p_dt)
                price_val = p.get("price")

                if p_local.date() == now.date():
                    today_prices.append((ts_str, price_val))
                elif p_local.date() == (now.date() + timedelta(days=1)):
                    tomorrow_prices.append((ts_str, price_val))
                elif p_local.date() > (now.date() + timedelta(days=1)):
                    future_prices.append(
                        {
                            "timestamp": ts_str,
                            "hour": p_local.hour,
                            "price": price_val,
                            ATTR_IS_CHEAP: p.get(ATTR_IS_CHEAP, False),
                            ATTR_IS_EXPENSIVE: p.get(ATTR_IS_EXPENSIVE, False),
                        }
                    )

                # Determine next-hour price (exact match on timestamp)
                if p_local == next_hour_start:
                    next_hour_price = p.get("price")

            attrs: Dict[str, Any] = {}
            if today_prices:
                attrs[ATTR_PRICES_TODAY] = [
                    {"time": ts, "price": price}
                    for ts, price in sorted(today_prices, key=lambda x: x[0])
                ]
            if tomorrow_prices:
                attrs[ATTR_PRICES_TOMORROW] = [
                    {"time": ts, "price": price}
                    for ts, price in sorted(tomorrow_prices, key=lambda x: x[0])
                ]
            if today_prices or tomorrow_prices:
                combined = sorted(today_prices + tomorrow_prices, key=lambda x: x[0])
                attrs[ATTR_PRICES] = [
                    {"time": ts, "price": price}
                    for ts, price in combined
                ]
            if future_prices:
                attrs[ATTR_PRICES_FUTURE] = sorted(future_prices, key=lambda x: x["timestamp"])
            if next_hour_price is not None:
                attrs[ATTR_NEXT_HOUR_PRICE] = next_hour_price

            # Flags for the current hour
            if branch.get(ATTR_IS_CHEAP) is not None:
                attrs[ATTR_IS_CHEAP] = branch.get(ATTR_IS_CHEAP, False)
            if branch.get(ATTR_IS_EXPENSIVE) is not None:
                attrs[ATTR_IS_EXPENSIVE] = branch.get(ATTR_IS_EXPENSIVE, False)

            return attrs
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Error extracting %s price attributes: %s", self._price_key, err)
            return {}

class PstrykBuyPriceSensor(_PstrykPriceSensor):
    """Sensor for Pstryk buy prices."""

    _attr_name = "Pstryk Buy Price"
    _attr_unique_id = "pstryk_buy_price"
    _attr_icon = "mdi:flash"
    _price_key = "buy"


class PstrykSellPriceSensor(_PstrykPriceSensor):
    """Sensor for Pstryk sell prices."""

    _attr_name = "Pstryk Sell Price"
    _attr_unique_id = "pstryk_sell_price"
    _attr_icon = "mdi:flash-outline"
    _price_key = "sell"


# -----------------------------------------------------------------------------
# "Next hour" sensors – expose the price that will be in effect during the
# upcoming hour. They reuse the data already fetched by the coordinator so they
# come at no extra API cost and give the user a ready-to-consume numeric entity
# without the need for additional template helpers.
# -----------------------------------------------------------------------------


class _PstrykNextHourMixin:
    """Mixin providing helper to calculate next hour price from coordinator."""

    def _get_next_hour_price(self, price_key: str) -> Optional[float]:
        """Return the price for the upcoming hour.

        :param price_key: either "buy" or "sell" so we know which branch of
                          the coordinator data to inspect.
        """
        if not self.coordinator.data or price_key not in self.coordinator.data:
            return None

        data = self.coordinator.data[price_key]
        prices = data.get("prices", [])

        # Define the timestamp (local) representing the beginning of the next
        # hour.
        now = dt_util.now()
        next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        # Iterate through the hourly frames and return the matching price.
        for item in prices:
            ts = item.get("timestamp")
            if not ts:
                continue

            price_dt = dt_util.parse_datetime(ts)
            if price_dt is None:
                continue

            price_local = dt_util.as_local(price_dt)
            if price_local == next_hour_start:
                return item.get("price")

        # If we could not find an exact match we return None so HA will treat
        # the sensor as unavailable instead of silently showing the current
        # hour again.
        return None


class PstrykBuyNextHourPriceSensor(_PstrykNextHourMixin, PstrykBaseSensor):
    """Sensor that shows the buy price for the upcoming hour."""

    _attr_name = "Pstryk Buy Price – Next Hour"
    _attr_unique_id = "pstryk_buy_price_next_hour"
    _attr_icon = "mdi:clock-fast"

    @property
    def native_value(self) -> Optional[float]:
        return self._get_next_hour_price("buy")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include the timestamp this price applies to so users can verify."""
        now = dt_util.now()
        next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return {
            "target_hour": next_hour_start.isoformat(),
        }


class PstrykSellNextHourPriceSensor(_PstrykNextHourMixin, PstrykBaseSensor):
    """Sensor that shows the sell price for the upcoming hour."""

    _attr_name = "Pstryk Sell Price – Next Hour"
    _attr_unique_id = "pstryk_sell_price_next_hour"
    _attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> Optional[float]:
        return self._get_next_hour_price("sell")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        now = dt_util.now()
        next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return {
            "target_hour": next_hour_start.isoformat(),
        }


# -----------------------------------------------------------------------------
# Energy cost sensor – shows the actual energy cost from the previous full hour
# based on meter readings and current energy prices
# -----------------------------------------------------------------------------


class PstrykBuyEnergyCostSensor(PstrykBaseSensor):
    """Sensor for energy buy cost from previous full hour."""

    _attr_name = "Pstryk Buy Energy Cost – Previous Hour"
    _attr_unique_id = "pstryk_energy_cost_buy_previous_hour"
    _attr_icon = "mdi:cash-multiple"
    _attr_native_unit_of_measurement = "PLN"
    _attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> Optional[float]:
        """Energy buy cost for the previous full hour."""
        if not self.coordinator.data or "energy_cost" not in self.coordinator.data:
            return None
        
        energy_cost_data = self.coordinator.data["energy_cost"]
        return energy_cost_data.get("previous_hour_cost")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include additional energy cost details."""
        if not self.coordinator.data or "energy_cost" not in self.coordinator.data:
            return {}
        
        energy_cost_data = self.coordinator.data["energy_cost"]
        frame_details = energy_cost_data.get("frame_details", {})
        
        attrs = {}
        
        # Add total cost if available
        if energy_cost_data.get("total_cost") is not None:
            attrs["total_cost"] = energy_cost_data["total_cost"]
        
        # Add frame timing details
        if frame_details.get("start"):
            start_dt = dt_util.parse_datetime(frame_details["start"])
            if start_dt:
                attrs["period_start"] = dt_util.as_local(start_dt).isoformat()
        
        if frame_details.get("end"):
            end_dt = dt_util.parse_datetime(frame_details["end"])
            if end_dt:
                attrs["period_end"] = dt_util.as_local(end_dt).isoformat()
        
        # Add live indicator
        if frame_details.get("is_live") is not None:
            attrs["is_live"] = frame_details["is_live"]
        
        # Add detailed cost breakdown
        cost_breakdown = frame_details.get("cost_breakdown", {})
        if cost_breakdown:
            attrs.update({
                "fae_cost": cost_breakdown.get("fae_cost"),
                "var_dist_cost_net": cost_breakdown.get("var_dist_cost_net"),
                "fix_dist_cost_net": cost_breakdown.get("fix_dist_cost_net"),
                "energy_cost_net": cost_breakdown.get("energy_cost_net"),
                "service_cost_net": cost_breakdown.get("service_cost_net"),
                "excise": cost_breakdown.get("excise"),
                "vat": cost_breakdown.get("vat"),
                "energy_sold_value": cost_breakdown.get("energy_sold_value"),
                "energy_balance_value": cost_breakdown.get("energy_balance_value"),
            })
        
        return attrs
    
class PstrykSellEnergyCostSensor(PstrykBaseSensor):
    """Sensor for energy sell value from previous full hour."""

    _attr_name = "Pstryk Sell Energy Cost – Previous Hour"
    _attr_unique_id = "pstryk_energy_cost_sell_previous_hour"
    _attr_icon = "mdi:cash-plus"
    _attr_native_unit_of_measurement = "PLN"
    _attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> Optional[float]:
        """Energy sell value for the previous full hour."""
        if not self.coordinator.data or "energy_cost" not in self.coordinator.data:
            return None
        
        energy_cost_data = self.coordinator.data["energy_cost"]
        frame_details = energy_cost_data.get("frame_details", {})
        cost_breakdown = frame_details.get("cost_breakdown", {})
        
        return cost_breakdown.get("energy_sold_value")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include additional energy sell details."""
        if not self.coordinator.data or "energy_cost" not in self.coordinator.data:
            return {}
        
        energy_cost_data = self.coordinator.data["energy_cost"]
        frame_details = energy_cost_data.get("frame_details", {})
        
        attrs = {}
        
        # Add frame timing details
        if frame_details.get("start"):
            start_dt = dt_util.parse_datetime(frame_details["start"])
            if start_dt:
                attrs["period_start"] = dt_util.as_local(start_dt).isoformat()
        
        if frame_details.get("end"):
            end_dt = dt_util.parse_datetime(frame_details["end"])
            if end_dt:
                attrs["period_end"] = dt_util.as_local(end_dt).isoformat()
        
        # Add live indicator
        if frame_details.get("is_live") is not None:
            attrs["is_live"] = frame_details["is_live"]
        
        # Add total energy sold value from API root level
        cost_breakdown = frame_details.get("cost_breakdown", {})
        if cost_breakdown.get("energy_sold_value") is not None:
            attrs["energy_sold_value"] = cost_breakdown.get("energy_sold_value")
        
        return attrs


# -----------------------------------------------------------------------------
# Energy usage sensors – shows actual energy usage and production from the previous full hour
# based on meter readings
# -----------------------------------------------------------------------------


class PstrykBuyEnergyUsageSensor(PstrykBaseSensor):
    """Sensor for energy usage from previous full hour."""

    _attr_name = "Pstryk Buy Energy Usage – Previous Hour"
    _attr_unique_id = "pstryk_buy_energy_usage_previous_hour"
    _attr_icon = "mdi:flash-auto"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Energy usage for the previous full hour."""
        if not self.coordinator.data or "energy_usage" not in self.coordinator.data:
            return None
        
        energy_usage_data = self.coordinator.data["energy_usage"]
        return energy_usage_data.get("previous_hour_usage")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include additional energy usage details."""
        if not self.coordinator.data or "energy_usage" not in self.coordinator.data:
            return {}
        
        energy_usage_data = self.coordinator.data["energy_usage"]
        frame_details = energy_usage_data.get("frame_details", {})
        
        attrs = {}
        
        # Add total usage if available
        if energy_usage_data.get("total_usage") is not None:
            attrs["total_usage"] = energy_usage_data["total_usage"]
        
        # Add frame timing details
        if frame_details.get("start"):
            start_dt = dt_util.parse_datetime(frame_details["start"])
            if start_dt:
                attrs["period_start"] = dt_util.as_local(start_dt).isoformat()
        
        if frame_details.get("end"):
            end_dt = dt_util.parse_datetime(frame_details["end"])
            if end_dt:
                attrs["period_end"] = dt_util.as_local(end_dt).isoformat()
        
        # Add live indicator
        if frame_details.get("is_live") is not None:
            attrs["is_live"] = frame_details["is_live"]
        
        # Add detailed usage breakdown
        usage_breakdown = frame_details.get("usage_breakdown", {})
        if usage_breakdown:
            attrs.update({
                "fae_usage": usage_breakdown.get("fae_usage"),
                "rae": usage_breakdown.get("rae"),
                "energy_balance": usage_breakdown.get("energy_balance"),
            })
        
        return attrs


class PstrykSellEnergyProductionSensor(PstrykBaseSensor):
    """Sensor for energy production from previous full hour."""

    _attr_name = "Pstryk Sell Energy Production – Previous Hour"
    _attr_unique_id = "pstryk_sell_energy_production_previous_hour"
    _attr_icon = "mdi:solar-power"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Energy production for the previous full hour."""
        if not self.coordinator.data or "energy_usage" not in self.coordinator.data:
            return None
        
        energy_usage_data = self.coordinator.data["energy_usage"]
        return energy_usage_data.get("previous_hour_production")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include additional energy production details."""
        if not self.coordinator.data or "energy_usage" not in self.coordinator.data:
            return {}
        
        energy_usage_data = self.coordinator.data["energy_usage"]
        frame_details = energy_usage_data.get("frame_details", {})
        
        attrs = {}
        
        # Add total production if available
        if energy_usage_data.get("total_production") is not None:
            attrs["total_production"] = energy_usage_data["total_production"]
        
        # Add frame timing details
        if frame_details.get("start"):
            start_dt = dt_util.parse_datetime(frame_details["start"])
            if start_dt:
                attrs["period_start"] = dt_util.as_local(start_dt).isoformat()
        
        if frame_details.get("end"):
            end_dt = dt_util.parse_datetime(frame_details["end"])
            if end_dt:
                attrs["period_end"] = dt_util.as_local(end_dt).isoformat()
        
        # Add live indicator
        if frame_details.get("is_live") is not None:
            attrs["is_live"] = frame_details["is_live"]
        
        # Add energy production value
        usage_breakdown = frame_details.get("usage_breakdown", {})
        if usage_breakdown:
            attrs.update({
                "fae_usage": usage_breakdown.get("fae_usage"),
                "rae": usage_breakdown.get("rae"),
                "energy_balance": usage_breakdown.get("energy_balance"),
            })
        
        return attrs