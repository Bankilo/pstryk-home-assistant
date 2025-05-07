"""Binary sensor platform for Pstryk.pl integration."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import COORDINATOR, DOMAIN
from .coordinator import PstrykDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Pstryk.pl binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    # Add binary sensors
    entities = [
        PstrykBuyCheapHourBinarySensor(coordinator),
        PstrykBuyExpensiveHourBinarySensor(coordinator),
        PstrykSellCheapHourBinarySensor(coordinator),
        PstrykSellExpensiveHourBinarySensor(coordinator),
    ]
    
    async_add_entities(entities)


class PstrykBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base Pstryk binary sensor entity."""

    def __init__(self, coordinator: PstrykDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
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


class PstrykBuyCheapHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk cheap buy hours."""

    _attr_name = "Pstryk Buy Cheap Hour"
    _attr_unique_id = "pstryk_buy_cheap_hour"
    _attr_icon = "mdi:currency-usd-off"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the current hour is flagged as cheap."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return None
            
        try:
            data = self.coordinator.data["buy"]
            return data.get("is_cheap", False)
        except Exception as error:
            _LOGGER.error("Error retrieving buy cheap flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return {}
            
        try:
            data = self.coordinator.data["buy"]
            prices = data.get("prices", [])
            
            # Find upcoming cheap hours
            cheap_hours = []
            for price_data in prices:
                if price_data.get("is_cheap", False):
                    cheap_hours.append({
                        "timestamp": price_data["timestamp"],
                        "hour": price_data["hour"],
                        "price": price_data["price"]
                    })
            
            return {"cheap_hours": cheap_hours[:24]}  # Limit to next 24 hours
        except Exception as error:
            _LOGGER.error("Error extracting buy cheap attributes: %s", error)
            return {}


class PstrykBuyExpensiveHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk expensive buy hours."""

    _attr_name = "Pstryk Buy Expensive Hour"
    _attr_unique_id = "pstryk_buy_expensive_hour"
    _attr_icon = "mdi:currency-usd"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the current hour is flagged as expensive."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return None
            
        try:
            data = self.coordinator.data["buy"]
            return data.get("is_expensive", False)
        except Exception as error:
            _LOGGER.error("Error retrieving buy expensive flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return {}
            
        try:
            data = self.coordinator.data["buy"]
            prices = data.get("prices", [])
            
            # Find upcoming expensive hours
            expensive_hours = []
            for price_data in prices:
                if price_data.get("is_expensive", False):
                    expensive_hours.append({
                        "timestamp": price_data["timestamp"],
                        "hour": price_data["hour"],
                        "price": price_data["price"]
                    })
            
            return {"expensive_hours": expensive_hours[:24]}  # Limit to next 24 hours
        except Exception as error:
            _LOGGER.error("Error extracting buy expensive attributes: %s", error)
            return {}


class PstrykSellCheapHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk cheap sell hours."""

    _attr_name = "Pstryk Sell Cheap Hour"
    _attr_unique_id = "pstryk_sell_cheap_hour"
    _attr_icon = "mdi:currency-usd-off"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the current hour is flagged as cheap."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return None
            
        try:
            data = self.coordinator.data["sell"]
            return data.get("is_cheap", False)
        except Exception as error:
            _LOGGER.error("Error retrieving sell cheap flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return {}
            
        try:
            data = self.coordinator.data["sell"]
            prices = data.get("prices", [])
            
            # Find upcoming cheap hours
            cheap_hours = []
            for price_data in prices:
                if price_data.get("is_cheap", False):
                    cheap_hours.append({
                        "timestamp": price_data["timestamp"],
                        "hour": price_data["hour"],
                        "price": price_data["price"]
                    })
            
            return {"cheap_hours": cheap_hours[:24]}  # Limit to next 24 hours
        except Exception as error:
            _LOGGER.error("Error extracting sell cheap attributes: %s", error)
            return {}


class PstrykSellExpensiveHourBinarySensor(PstrykBaseBinarySensor):
    """Binary sensor for Pstryk expensive sell hours."""

    _attr_name = "Pstryk Sell Expensive Hour"
    _attr_unique_id = "pstryk_sell_expensive_hour"
    _attr_icon = "mdi:currency-usd"
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the current hour is flagged as expensive."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return None
            
        try:
            data = self.coordinator.data["sell"]
            return data.get("is_expensive", False)
        except Exception as error:
            _LOGGER.error("Error retrieving sell expensive flag: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return {}
            
        try:
            data = self.coordinator.data["sell"]
            prices = data.get("prices", [])
            
            # Find upcoming expensive hours
            expensive_hours = []
            for price_data in prices:
                if price_data.get("is_expensive", False):
                    expensive_hours.append({
                        "timestamp": price_data["timestamp"],
                        "hour": price_data["hour"],
                        "price": price_data["price"]
                    })
            
            return {"expensive_hours": expensive_hours[:24]}  # Limit to next 24 hours
        except Exception as error:
            _LOGGER.error("Error extracting sell expensive attributes: %s", error)
            return {}