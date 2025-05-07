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

from .const import COORDINATOR, DOMAIN
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
    ]
    
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


class PstrykBuyPriceSensor(PstrykBaseSensor):
    """Sensor for Pstryk buy prices."""

    _attr_name = "Pstryk Buy Price"
    _attr_unique_id = "pstryk_buy_price"
    _attr_icon = "mdi:flash"

    @property
    def native_value(self) -> Optional[float]:
        """Return the current price."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return None
            
        try:
            data = self.coordinator.data["buy"]
            return data.get("current_price")
        except Exception as error:
            _LOGGER.error("Error retrieving buy price: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return {}
            
        try:
            now = dt_util.now()
            data = self.coordinator.data["buy"]
            prices = data.get("prices", [])
            
            # Group prices by date
            today_prices = []
            tomorrow_prices = []
            next_hour_price = None
            
            for price_data in prices:
                timestamp = price_data.get("timestamp")
                if not timestamp:
                    continue
                    
                price_datetime = dt_util.parse_datetime(timestamp)
                if not price_datetime:
                    continue
                    
                price = price_data.get("price")
                if price is None:
                    continue
                    
                price_local = dt_util.as_local(price_datetime)
                
                # Check if price is for today or tomorrow
                if price_local.date() == now.date():
                    today_prices.append({
                        "hour": price_local.hour,
                        "price": price
                    })
                elif price_local.date() == (now.date() + timedelta(days=1)):
                    tomorrow_prices.append({
                        "hour": price_local.hour,
                        "price": price
                    })
                    
                # Check if price is for next hour
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                if price_local.hour == next_hour.hour and price_local.date() == next_hour.date():
                    next_hour_price = price
            
            attributes = {}
            if today_prices:
                attributes["prices_today"] = sorted(today_prices, key=lambda x: x["hour"])
            if tomorrow_prices:
                attributes["prices_tomorrow"] = sorted(tomorrow_prices, key=lambda x: x["hour"])
            if next_hour_price is not None:
                attributes["next_hour_price"] = next_hour_price
                
            return attributes
        except Exception as error:
            _LOGGER.error("Error extracting buy price attributes: %s", error)
            return {}


class PstrykSellPriceSensor(PstrykBaseSensor):
    """Sensor for Pstryk sell prices."""

    _attr_name = "Pstryk Sell Price"
    _attr_unique_id = "pstryk_sell_price"
    _attr_icon = "mdi:flash-outline"

    @property
    def native_value(self) -> Optional[float]:
        """Return the current price."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return None
            
        try:
            data = self.coordinator.data["sell"]
            return data.get("current_price")
        except Exception as error:
            _LOGGER.error("Error retrieving sell price: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return {}
            
        try:
            now = dt_util.now()
            data = self.coordinator.data["sell"]
            prices = data.get("prices", [])
            
            # Group prices by date
            today_prices = []
            tomorrow_prices = []
            next_hour_price = None
            
            for price_data in prices:
                timestamp = price_data.get("timestamp")
                if not timestamp:
                    continue
                    
                price_datetime = dt_util.parse_datetime(timestamp)
                if not price_datetime:
                    continue
                    
                price = price_data.get("price")
                if price is None:
                    continue
                    
                price_local = dt_util.as_local(price_datetime)
                
                # Check if price is for today or tomorrow
                if price_local.date() == now.date():
                    today_prices.append({
                        "hour": price_local.hour,
                        "price": price
                    })
                elif price_local.date() == (now.date() + timedelta(days=1)):
                    tomorrow_prices.append({
                        "hour": price_local.hour,
                        "price": price
                    })
                    
                # Check if price is for next hour
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                if price_local.hour == next_hour.hour and price_local.date() == next_hour.date():
                    next_hour_price = price
            
            attributes = {}
            if today_prices:
                attributes["prices_today"] = sorted(today_prices, key=lambda x: x["hour"])
            if tomorrow_prices:
                attributes["prices_tomorrow"] = sorted(tomorrow_prices, key=lambda x: x["hour"])
            if next_hour_price is not None:
                attributes["next_hour_price"] = next_hour_price
                
            return attributes
        except Exception as error:
            _LOGGER.error("Error extracting sell price attributes: %s", error)
            return {}