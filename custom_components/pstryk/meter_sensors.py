"""Meter sensors for Pstryk.pl integration."""
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN
from .coordinator import PstrykDataUpdateCoordinator, _get_meter_sensor_value


class PstrykMeterBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Pstryk meter data."""

    def __init__(self, coordinator: PstrykDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, "pstryk_meter")},
            "name": "Pstryk Meter",
            "manufacturer": "Pstryk.pl",
            "model": "Smart Meter",
            "sw_version": "1.0",
        }

    @property
    def available(self) -> bool:
        """Return True if meter data is available."""
        return (
            self.coordinator.last_update_success 
            and self.coordinator.data is not None 
            and "meter_state" in self.coordinator.data
        )


class PstrykEnergyPowerSensor(PstrykMeterBaseSensor):
    """Sensor for current energy power from meter (activePower)."""

    _attr_name = "Pstryk Energy Power"
    _attr_unique_id = "pstryk_energy_power"
    _attr_icon = "mdi:flash"
    _attr_native_unit_of_measurement = "kW"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return current active power in kW."""
        if not self.available:
            return None
        
        meter_data = self.coordinator.data.get("meter_state")
        # Get activePower in W for sensor id=0
        power_w = _get_meter_sensor_value(meter_data, 0, "activePower")
        
        if power_w is not None:
            # Convert from W to kW
            return round(power_w / 1000, 3)
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include additional power details."""
        if not self.available:
            return {}
        
        meter_data = self.coordinator.data.get("meter_state")
        attrs = {}
        
        # Add raw power value in watts
        power_w = _get_meter_sensor_value(meter_data, 0, "activePower")
        if power_w is not None:
            attrs["power_watts"] = power_w
        
        # Add reactive and apparent power if available
        reactive_power = _get_meter_sensor_value(meter_data, 0, "reactivePower")
        if reactive_power is not None:
            attrs["reactive_power_var"] = reactive_power
        
        apparent_power = _get_meter_sensor_value(meter_data, 0, "apparentPower")
        if apparent_power is not None:
            attrs["apparent_power_va"] = apparent_power
        
        return attrs


class PstrykCurrentSensor(PstrykMeterBaseSensor):
    """Sensor for electrical current from meter."""

    _attr_name = "Pstryk Current"
    _attr_unique_id = "pstryk_current"
    _attr_icon = "mdi:current-ac"
    _attr_native_unit_of_measurement = "A"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return current in amperes."""
        if not self.available:
            return None
        
        meter_data = self.coordinator.data.get("meter_state")
        # Get current for sensor id=0 - value seems to be in mA
        current_ma = _get_meter_sensor_value(meter_data, 0, "current")
        
        if current_ma is not None:
            # Convert from mA to A
            return round(current_ma / 1000, 2)
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Include additional current details."""
        if not self.available:
            return {}
        
        meter_data = self.coordinator.data.get("meter_state")
        attrs = {}
        
        # Add raw current value in mA
        current_ma = _get_meter_sensor_value(meter_data, 0, "current")
        if current_ma is not None:
            attrs["current_milliamps"] = current_ma
        
        # Add voltage and frequency if available
        voltage = _get_meter_sensor_value(meter_data, 0, "voltage")
        if voltage is not None:
            # Voltage seems to be in centivolts (2453 = 245.3V)
            attrs["voltage_v"] = round(voltage / 100, 1)
        
        frequency = _get_meter_sensor_value(meter_data, 0, "frequency")
        if frequency is not None:
            # Frequency seems to be in millihertz (49970 = 49.97 Hz)
            attrs["frequency_hz"] = round(frequency / 1000, 2)
        
        return attrs 