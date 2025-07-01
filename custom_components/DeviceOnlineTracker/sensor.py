"""Sensor platform for device_online_tracker."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, DeviceOnlineTrackerEntity

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([
        DeviceOnlineTimeSensor(coordinator, config_entry)
    ])

class DeviceOnlineTimeSensor(DeviceOnlineTrackerEntity, SensorEntity):
    """Representation of a Device Online Time Sensor."""

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, "online_time")
        self._attr_native_unit_of_measurement = "min"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_icon = "mdi:timer"
        self._attr_name = "Online Time"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data and self.coordinator.data.get("online_time", 0) 