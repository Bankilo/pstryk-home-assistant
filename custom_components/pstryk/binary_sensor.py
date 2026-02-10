"""Binary sensor platform for Pstryk.pl integration."""
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
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
    ATTR_CHEAP_HOURS,
    ATTR_IS_CHEAP,
    ATTR_IS_EXPENSIVE,
    ATTR_EXPENSIVE_HOURS,
    DOMAIN,
)
from .coordinator import PstrykDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: PstrykConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Pstryk.pl binary sensor platform."""
    coordinator = entry.runtime_data

    entities = [
        PstrykBuyCheapHourBinarySensor(coordinator),
        PstrykBuyExpensiveHourBinarySensor(coordinator),
        PstrykSellCheapHourBinarySensor(coordinator),
        PstrykSellExpensiveHourBinarySensor(coordinator),
    ]

    async_add_entities(entities)


class PstrykBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base Pstryk binary sensor entity."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({ATTR_CHEAP_HOURS, ATTR_EXPENSIVE_HOURS})

    def __init__(self, coordinator: PstrykDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
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


class PstrykBuyCheapHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk cheap buy hours."""

    _attr_translation_key = "buy_cheap_hour"
    _attr_unique_id = "pstryk_buy_cheap_hour"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> bool | None:
        """Return true if the current hour is flagged as cheap."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return None

        try:
            data = self.coordinator.data["buy"]
            return data.get(ATTR_IS_CHEAP, False)
        except Exception as error:
            _LOGGER.error("Error retrieving buy cheap flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return {}

        try:
            data = self.coordinator.data["buy"]
            prices = data.get("prices", [])

            cheap_hours = []
            for price_data in prices:
                if price_data.get(ATTR_IS_CHEAP, False):
                    price_datetime = dt_util.parse_datetime(price_data["timestamp"])
                    if price_datetime and price_datetime >= dt_util.now():
                        cheap_hours.append({
                            "timestamp": price_data["timestamp"],
                            "hour": price_data["hour"],
                            "price": price_data["price"],
                            "date": dt_util.as_local(price_datetime).date().isoformat()
                        })

            return {ATTR_CHEAP_HOURS: sorted(cheap_hours, key=lambda x: x["timestamp"])}
        except Exception as error:
            _LOGGER.error("Error extracting buy cheap attributes: %s", error)
            return {}


class PstrykBuyExpensiveHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk expensive buy hours."""

    _attr_translation_key = "buy_expensive_hour"
    _attr_unique_id = "pstryk_buy_expensive_hour"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> bool | None:
        """Return true if the current hour is flagged as expensive."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return None

        try:
            data = self.coordinator.data["buy"]
            return data.get(ATTR_IS_EXPENSIVE, False)
        except Exception as error:
            _LOGGER.error("Error retrieving buy expensive flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return {}

        try:
            data = self.coordinator.data["buy"]
            prices = data.get("prices", [])

            expensive_hours = []
            for price_data in prices:
                if price_data.get(ATTR_IS_EXPENSIVE, False):
                    price_datetime = dt_util.parse_datetime(price_data["timestamp"])
                    if price_datetime and price_datetime >= dt_util.now():
                        expensive_hours.append({
                            "timestamp": price_data["timestamp"],
                            "hour": price_data["hour"],
                            "price": price_data["price"],
                            "date": dt_util.as_local(price_datetime).date().isoformat()
                        })

            return {ATTR_EXPENSIVE_HOURS: sorted(expensive_hours, key=lambda x: x["timestamp"])}
        except Exception as error:
            _LOGGER.error("Error extracting buy expensive attributes: %s", error)
            return {}


class PstrykSellCheapHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk cheap sell hours."""

    _attr_translation_key = "sell_cheap_hour"
    _attr_unique_id = "pstryk_sell_cheap_hour"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> bool | None:
        """Return true if the current hour is flagged as cheap."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return None

        try:
            data = self.coordinator.data["sell"]
            return data.get(ATTR_IS_CHEAP, False)
        except Exception as error:
            _LOGGER.error("Error retrieving sell cheap flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return {}

        try:
            data = self.coordinator.data["sell"]
            prices = data.get("prices", [])

            cheap_hours = []
            for price_data in prices:
                if price_data.get(ATTR_IS_CHEAP, False):
                    price_datetime = dt_util.parse_datetime(price_data["timestamp"])
                    if price_datetime and price_datetime >= dt_util.now():
                        cheap_hours.append({
                            "timestamp": price_data["timestamp"],
                            "hour": price_data["hour"],
                            "price": price_data["price"],
                            "date": dt_util.as_local(price_datetime).date().isoformat()
                        })

            return {ATTR_CHEAP_HOURS: sorted(cheap_hours, key=lambda x: x["timestamp"])}
        except Exception as error:
            _LOGGER.error("Error extracting sell cheap attributes: %s", error)
            return {}


class PstrykSellExpensiveHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk expensive sell hours."""

    _attr_translation_key = "sell_expensive_hour"
    _attr_unique_id = "pstryk_sell_expensive_hour"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> bool | None:
        """Return true if the current hour is flagged as expensive."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return None

        try:
            data = self.coordinator.data["sell"]
            return data.get(ATTR_IS_EXPENSIVE, False)
        except Exception as error:
            _LOGGER.error("Error retrieving sell expensive flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return {}

        try:
            data = self.coordinator.data["sell"]
            prices = data.get("prices", [])

            expensive_hours = []
            for price_data in prices:
                if price_data.get(ATTR_IS_EXPENSIVE, False):
                    price_datetime = dt_util.parse_datetime(price_data["timestamp"])
                    if price_datetime and price_datetime >= dt_util.now():
                        expensive_hours.append({
                            "timestamp": price_data["timestamp"],
                            "hour": price_data["hour"],
                            "price": price_data["price"],
                            "date": dt_util.as_local(price_datetime).date().isoformat()
                        })

            return {ATTR_EXPENSIVE_HOURS: sorted(expensive_hours, key=lambda x: x["timestamp"])}
        except Exception as error:
            _LOGGER.error("Error extracting sell expensive attributes: %s", error)
            return {}
