"""Sensor platform for Pstryk.pl integration."""
from datetime import datetime, timedelta
import logging
from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
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
            
        # Logic to extract current price from the data
        # This will need to be adjusted based on the actual API response structure
        try:
            now = datetime.now().astimezone()
            now_utc = now.astimezone(datetime.timezone.utc)
            current_hour_utc = now_utc.replace(minute=0, second=0, microsecond=0)
            data = self.coordinator.data["buy"]
            
            # Assuming data contains a list of hourly prices
            # Find the current hour's price
            current_price = None
            for price_data in data.get("prices", []):
                price_datetime = datetime.fromisoformat(price_data.get("timestamp"))
                # Convert to UTC for comparison
                if price_datetime.tzinfo is None:
                    price_datetime = price_datetime.replace(tzinfo=datetime.timezone.utc)
                if price_datetime == current_hour_utc:
                    current_price = price_data.get("price")
                    break
                    
            return current_price
        except (KeyError, ValueError, AttributeError) as error:
            _LOGGER.error("Error extracting buy price: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "buy" not in self.coordinator.data:
            return {}
            
        # Extract additional data for the attributes
        attributes = {}
        
        # This will need to be adjusted based on the actual API response structure
        try:
            now = datetime.now().astimezone()
            now_utc = now.astimezone(datetime.timezone.utc)
            next_hour_utc = (now_utc.replace(minute=0, second=0, microsecond=0) + 
                           timedelta(hours=1))
            data = self.coordinator.data["buy"]
            
            # Extract today's and tomorrow's prices
            today_prices = []
            tomorrow_prices = []
            next_hour_price = None
            
            for price_data in data.get("prices", []):
                price_datetime = datetime.fromisoformat(price_data.get("timestamp"))
                price = price_data.get("price")
                
                # Convert to UTC for comparison
                if price_datetime.tzinfo is None:
                    price_datetime = price_datetime.replace(tzinfo=datetime.timezone.utc)
                
                if price_datetime.date() == now_utc.date():
                    today_prices.append({
                        "hour": price_datetime.hour,
                        "price": price
                    })
                elif price_datetime.date() == (now_utc.date() + timedelta(days=1)):
                    tomorrow_prices.append({
                        "hour": price_datetime.hour,
                        "price": price
                    })
                    
                if price_datetime == next_hour_utc:
                    next_hour_price = price
            
            if today_prices:
                attributes["prices_today"] = today_prices
            if tomorrow_prices:
                attributes["prices_tomorrow"] = tomorrow_prices
            if next_hour_price is not None:
                attributes["next_hour_price"] = next_hour_price
                
            return attributes
        except (KeyError, ValueError, AttributeError) as error:
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
            
        # Logic to extract current price from the data
        # This will need to be adjusted based on the actual API response structure
        try:
            now = datetime.now().astimezone()
            now_utc = now.astimezone(datetime.timezone.utc)
            current_hour_utc = now_utc.replace(minute=0, second=0, microsecond=0)
            data = self.coordinator.data["sell"]
            
            # Assuming data contains a list of hourly prices
            # Find the current hour's price
            current_price = None
            for price_data in data.get("prices", []):
                price_datetime = datetime.fromisoformat(price_data.get("timestamp"))
                # Convert to UTC for comparison
                if price_datetime.tzinfo is None:
                    price_datetime = price_datetime.replace(tzinfo=datetime.timezone.utc)
                if price_datetime == current_hour_utc:
                    current_price = price_data.get("price")
                    break
                    
            return current_price
        except (KeyError, ValueError, AttributeError) as error:
            _LOGGER.error("Error extracting sell price: %s", error)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "sell" not in self.coordinator.data:
            return {}
            
        # Extract additional data for the attributes
        attributes = {}
        
        # This will need to be adjusted based on the actual API response structure
        try:
            now = datetime.now().astimezone()
            now_utc = now.astimezone(datetime.timezone.utc)
            next_hour_utc = (now_utc.replace(minute=0, second=0, microsecond=0) + 
                           timedelta(hours=1))
            data = self.coordinator.data["sell"]
            
            # Extract today's and tomorrow's prices
            today_prices = []
            tomorrow_prices = []
            next_hour_price = None
            
            for price_data in data.get("prices", []):
                price_datetime = datetime.fromisoformat(price_data.get("timestamp"))
                price = price_data.get("price")
                
                # Convert to UTC for comparison
                if price_datetime.tzinfo is None:
                    price_datetime = price_datetime.replace(tzinfo=datetime.timezone.utc)
                
                if price_datetime.date() == now_utc.date():
                    today_prices.append({
                        "hour": price_datetime.hour,
                        "price": price
                    })
                elif price_datetime.date() == (now_utc.date() + timedelta(days=1)):
                    tomorrow_prices.append({
                        "hour": price_datetime.hour,
                        "price": price
                    })
                    
                if price_datetime == next_hour_utc:
                    next_hour_price = price
            
            if today_prices:
                attributes["prices_today"] = today_prices
            if tomorrow_prices:
                attributes["prices_tomorrow"] = tomorrow_prices
            if next_hour_price is not None:
                attributes["next_hour_price"] = next_hour_price
                
            return attributes
        except (KeyError, ValueError, AttributeError) as error:
            _LOGGER.error("Error extracting sell price attributes: %s", error)
            return {}