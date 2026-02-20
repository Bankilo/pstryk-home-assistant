"""Sensor platform for Pstryk.pl integration."""
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.util import dt as dt_util

from . import PstrykConfigEntry
from .const import (
    ATTR_IS_CHEAP,
    ATTR_IS_EXPENSIVE,
    ATTR_NEXT_HOUR_PRICE,
    ATTR_PRICES,
    ATTR_PRICES_FUTURE,
    ATTR_PRICES_TODAY,
    ATTR_PRICES_TOMORROW,
    DOMAIN,
)
from .coordinator import PstrykDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: PstrykConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Pstryk.pl sensor platform."""
    coordinator = entry.runtime_data

    entities = [
        PstrykBuyPriceSensor(coordinator),
        PstrykSellPriceSensor(coordinator),
        PstrykBuyNextHourPriceSensor(coordinator),
        PstrykSellNextHourPriceSensor(coordinator),
    ]

    async_add_entities(entities)


class PstrykBaseSensor(CoordinatorEntity, SensorEntity):
    """Base Pstryk sensor entity."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN/kWh"

    def __init__(self, coordinator: PstrykDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "pstryk_energy_prices")},
            name="Pstryk Energy Prices",
            manufacturer="Pstryk.pl",
            model="API",
            sw_version="1.0",
        )


# -----------------------------------------------------------------------------
# Generic hourly price sensor
# -----------------------------------------------------------------------------


class _PstrykPriceSensor(PstrykBaseSensor):
    """Shared implementation for buy/sell price sensors."""

    _unrecorded_attributes = frozenset(
        {ATTR_PRICES_TODAY, ATTR_PRICES_TOMORROW, ATTR_PRICES, ATTR_PRICES_FUTURE, ATTR_IS_CHEAP, ATTR_IS_EXPENSIVE}
    )

    # Must be set by subclass ("buy" | "sell")
    _price_key: str = "buy"

    # -------------------- Helpers --------------------
    def _price_branch(self) -> dict | None:
        """Return the nested dict for the configured price type."""
        if not self.coordinator.data or self._price_key not in self.coordinator.data:
            return None
        return self.coordinator.data[self._price_key]

    # -------------------- Home Assistant properties --------------------
    @property
    def native_value(self) -> float | None:
        """Current price for the ongoing hour."""
        branch = self._price_branch()
        if branch is None:
            return None
        value = branch.get("current_price")
        return float(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
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
            next_hour_price: float | None = None

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

            attrs: dict[str, Any] = {}
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

    _attr_translation_key = "buy_price"
    _attr_unique_id = "pstryk_buy_price"
    _price_key = "buy"


class PstrykSellPriceSensor(_PstrykPriceSensor):
    """Sensor for Pstryk sell prices."""

    _attr_translation_key = "sell_price"
    _attr_unique_id = "pstryk_sell_price"
    _price_key = "sell"


# -----------------------------------------------------------------------------
# "Next hour" sensors – expose the price that will be in effect during the
# upcoming hour. They reuse the data already fetched by the coordinator so they
# come at no extra API cost and give the user a ready-to-consume numeric entity
# without the need for additional template helpers.
# -----------------------------------------------------------------------------


class _PstrykNextHourMixin:
    """Mixin providing helper to calculate next hour price from coordinator."""

    def _get_next_hour_price(self, price_key: str) -> float | None:
        """Return the price for the upcoming hour.

        :param price_key: either "buy" or "sell" so we know which branch of
                          the coordinator data to inspect.
        """
        if not self.coordinator.data or price_key not in self.coordinator.data:
            return None

        data = self.coordinator.data[price_key]
        prices = data.get("prices", [])

        now = dt_util.now()
        next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

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

        return None


class PstrykBuyNextHourPriceSensor(_PstrykNextHourMixin, PstrykBaseSensor):
    """Sensor that shows the buy price for the upcoming hour."""

    _attr_translation_key = "buy_price_next_hour"
    _attr_unique_id = "pstryk_buy_price_next_hour"
    _unrecorded_attributes = frozenset({"target_hour"})

    @property
    def native_value(self) -> float | None:
        return self._get_next_hour_price("buy")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include the timestamp this price applies to so users can verify."""
        now = dt_util.now()
        next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return {
            "target_hour": next_hour_start.isoformat(),
        }


class PstrykSellNextHourPriceSensor(_PstrykNextHourMixin, PstrykBaseSensor):
    """Sensor that shows the sell price for the upcoming hour."""

    _attr_translation_key = "sell_price_next_hour"
    _attr_unique_id = "pstryk_sell_price_next_hour"
    _unrecorded_attributes = frozenset({"target_hour"})

    @property
    def native_value(self) -> float | None:
        return self._get_next_hour_price("sell")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = dt_util.now()
        next_hour_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return {
            "target_hour": next_hour_start.isoformat(),
        }
