"""Device Online Tracker integration."""
import logging
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
_LOGGER.info("Loading Device Online Tracker integration")

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    Platform
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
import voluptuous as vol

from icmplib import async_ping

DOMAIN = "device_online_tracker"
SCAN_INTERVAL = timedelta(minutes=1)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_data"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

def get_storage_path(hass: HomeAssistant) -> str:
    """Get the path to the storage file."""
    return hass.config.path(f"{STORAGE_KEY}.json")

def load_stored_data(hass: HomeAssistant, entry_id: str) -> Dict:
    """Load stored data from disk."""
    try:
        storage_path = get_storage_path(hass)
        if os.path.exists(storage_path):
            with open(storage_path, "r", encoding="utf-8") as file:
                stored_data = json.load(file)
                if entry_id in stored_data:
                    stored_date = datetime.strptime(
                        stored_data[entry_id]["last_date"],
                        "%Y-%m-%d"
                    ).date()
                    if stored_date == datetime.now().date():
                        return stored_data[entry_id]
    except Exception as err:
        _LOGGER.error("Error loading stored data: %s", err)
    
    return {
        "online_time": 0,
        "last_check": None,
        "last_date": datetime.now().date().isoformat(),
        "is_online": False
    }

def save_data(hass: HomeAssistant, entry_id: str, data: Dict) -> None:
    """Save data to disk."""
    try:
        storage_path = get_storage_path(hass)
        stored_data = {}
        
        if os.path.exists(storage_path):
            with open(storage_path, "r", encoding="utf-8") as file:
                stored_data = json.load(file)
        
        data_to_store = data.copy()
        data_to_store["last_date"] = data["last_date"].isoformat()
        if data_to_store["last_check"]:
            data_to_store["last_check"] = data_to_store["last_check"].isoformat()
        
        stored_data[entry_id] = data_to_store
        
        with open(storage_path, "w", encoding="utf-8") as file:
            json.dump(stored_data, file)
    except Exception as err:
        _LOGGER.error("Error saving data: %s", err)

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the Device Online Tracker component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Device Online Tracker from a config entry."""
    device_name = entry.data[CONF_NAME]
    host = entry.data[CONF_HOST]
    
    device_data = load_stored_data(hass, entry.entry_id)
    if isinstance(device_data["last_date"], str):
        device_data["last_date"] = datetime.strptime(
            device_data["last_date"],
            "%Y-%m-%d"
        ).date()
    
    async def async_update_data():
        """Fetch data from API endpoint."""
        try:
            host_ping = await async_ping(host, count=1, timeout=2)
            is_online = host_ping.is_alive
            
            current_date = datetime.now().date()
            
            if current_date != device_data["last_date"]:
                device_data["online_time"] = 0
                device_data["last_date"] = current_date
            
            if is_online:
                device_data["online_time"] += 1
            
            device_data["is_online"] = is_online
            device_data["last_check"] = datetime.now()
            
            save_data(hass, entry.entry_id, device_data)
            
            return device_data
            
        except Exception as err:
            _LOGGER.error("Error updating device status: %s", err)
            return device_data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"device_{device_name}",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

class DeviceOnlineTrackerEntity(CoordinatorEntity):
    """Representation of a Device Online Tracker entity."""

    def __init__(self, coordinator, config_entry, entity_type):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.entity_type = entity_type
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_type}"
        
    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.config_entry.data[CONF_NAME],
            manufacturer="捣鼓程序员",
            model="Device Online Tracker",
            sw_version="1.0",
        ) 
