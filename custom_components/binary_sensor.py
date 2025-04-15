"""Binary sensor platform for device_online_tracker."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
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
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([
        DeviceOnlineStatusSensor(coordinator, config_entry)
    ])

class DeviceOnlineStatusSensor(DeviceOnlineTrackerEntity, BinarySensorEntity):
    """Representation of a Device Online Status Sensor."""

    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, "status")
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_name = "Status"

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.data and self.coordinator.data.get("is_online") 