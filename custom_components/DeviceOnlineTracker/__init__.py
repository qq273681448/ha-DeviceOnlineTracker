"""Device Online Tracker integration."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, cast, Tuple, Optional
import json
import subprocess
import re
import netifaces

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
_LOGGER.info("Loading Device Online Tracker integration")

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    Platform
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.storage import Store
import voluptuous as vol

from icmplib import async_ping

DOMAIN = "device_online_tracker"
SCAN_INTERVAL = timedelta(minutes=1)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_data"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the Device Online Tracker component."""
    hass.data.setdefault(DOMAIN, {})
    return True

def get_default_interface() -> str:
    """获取默认网络接口
    
    Returns:
        str: 默认网络接口名称
    """
    try:
        # 获取默认网关接口
        gateways = netifaces.gateways()
        default_gateway = gateways['default'][netifaces.AF_INET][1]
        _LOGGER.debug("获取到默认网络接口: %s", default_gateway)
        return default_gateway
    except Exception as err:
        _LOGGER.error("获取默认网络接口失败: %s", err)
        # 如果获取失败，返回第一个非回环接口
        for interface in netifaces.interfaces():
            if interface != 'lo':
                _LOGGER.debug("使用备选网络接口: %s", interface)
                return interface
        return 'eth0'  # 最后的默认值

def get_ip_from_mac(mac_address: str) -> Optional[str]:
    """通过MAC地址获取IP地址
    
    Args:
        mac_address: MAC地址
        
    Returns:
        Optional[str]: IP地址，如果未找到则返回None
    """
    try:
        # 获取ARP表
        result = subprocess.run(
            ["ip", "neigh", "show"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # 将MAC地址转换为小写并替换分隔符
        mac_pattern = mac_address.lower().replace(':', '')
        
        # 在ARP表中查找MAC地址
        for line in result.stdout.splitlines():
            if mac_pattern in line.lower().replace(':', ''):
                # 提取IP地址
                ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                if ip_match:
                    ip_address = ip_match.group(1)
                    _LOGGER.debug("找到MAC地址 %s 对应的IP地址: %s", mac_address, ip_address)
                    return ip_address
        
        _LOGGER.warning("未找到MAC地址 %s 对应的IP地址", mac_address)
        return None
    except Exception as err:
        _LOGGER.error("获取IP地址时出错: %s", err)
        return None

async def check_device_status(host: str) -> Tuple[bool, datetime]:
    """检查设备在线状态
    
    Args:
        host: 设备主机地址或MAC地址（格式：xx:xx:xx:xx:xx:xx）
        
    Returns:
        Tuple[bool, datetime]: 返回设备是否在线和检查时间
    """
    try:
        current_time = datetime.now()
        
        # 检查是否为MAC地址
        if ":" in host:
            # 先获取MAC地址对应的IP
            ip_address = get_ip_from_mac(host)
            if ip_address:
                _LOGGER.debug("开始检测MAC地址: %s, 对应IP: %s", host, ip_address)
                # 使用ping检测IP地址
                host_ping = await async_ping(ip_address, count=1, timeout=2)
                is_online = host_ping.is_alive
                _LOGGER.debug("MAC地址 %s (IP: %s) 检测结果: %s", 
                            host, ip_address, "在线" if is_online else "离线")
            else:
                _LOGGER.warning("无法获取MAC地址 %s 对应的IP地址，尝试直接ping", host)
                # 如果无法获取IP，尝试直接ping MAC地址
                try:
                    interface = get_default_interface()
                    result = subprocess.run(
                        ["ping", "-c", "1", "-w", "2", host],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    is_online = result.returncode == 0
                except Exception as err:
                    _LOGGER.error("ping MAC地址失败: %s", err)
                    is_online = False
        else:
            # 使用ping检测IP地址
            _LOGGER.debug("开始检测IP地址: %s", host)
            host_ping = await async_ping(host, count=1, timeout=2)
            is_online = host_ping.is_alive
            _LOGGER.debug("IP地址 %s 检测结果: %s", host, "在线" if is_online else "离线")
            
        return is_online, current_time
    except Exception as err:
        _LOGGER.error("检查设备状态时出错: %s", err)
        return False, datetime.now()

async def update_device_data(device_data: Dict[str, Any], host: str, store: Store, entry_id: str) -> Dict[str, Any]:
    """更新设备数据
    
    Args:
        device_data: 当前设备数据
        host: 设备主机地址
        store: 存储对象
        entry_id: 配置条目ID
        
    Returns:
        Dict[str, Any]: 更新后的设备数据
    """
    try:
        is_online, current_time = await check_device_status(host)
        current_date = current_time.date()
        
        # 如果是新的一天，重置计时
        if current_date != device_data["last_date"]:
            device_data["online_time"] = 0
            device_data["last_date"] = current_date
        
        # 计算在线时间
        if device_data.get("last_check") and device_data.get("is_online") and is_online:
            time_diff = (current_time - device_data["last_check"]).total_seconds() / 60
            device_data["online_time"] += time_diff
        
        device_data["is_online"] = is_online
        device_data["last_check"] = current_time
        device_data["online_time"] = round(device_data.get("online_time", 0))
        
        # 保存数据到持久存储
        try:
            stored_data = await store.async_load() or {}
            save_data = {
                "online_time": device_data["online_time"],
                "last_date": device_data["last_date"].isoformat(),
                "is_online": device_data["is_online"]
            }
            
            if device_data["last_check"]:
                save_data["last_check"] = device_data["last_check"].isoformat()
            
            stored_data[entry_id] = save_data
            await store.async_save(stored_data)
        except Exception as save_err:
            _LOGGER.error("保存数据时出错: %s", save_err)
        
        return device_data
    except Exception as err:
        _LOGGER.error("更新设备数据时出错: %s", err)
        return device_data

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Device Online Tracker from a config entry."""
    device_name = entry.data[CONF_NAME]
    host = entry.data[CONF_HOST]
    
    # 创建存储对象
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    
    # 初始化设备数据
    device_data = {
        "online_time": 0,
        "last_check": None,
        "last_date": datetime.now().date().isoformat(),
        "is_online": False
    }
    
    # 尝试从存储加载数据
    try:
        stored_data = await store.async_load()
        if stored_data and entry.entry_id in stored_data:
            entry_data = stored_data[entry.entry_id]
            
            # 检查是否是同一天的数据
            stored_date = datetime.strptime(
                entry_data["last_date"],
                "%Y-%m-%d"
            ).date()
            
            if stored_date == datetime.now().date():
                device_data["online_time"] = entry_data["online_time"]
                device_data["last_date"] = stored_date.isoformat()
                
                if entry_data.get("last_check"):
                    device_data["last_check"] = datetime.fromisoformat(entry_data["last_check"])
                
                _LOGGER.info("已从存储恢复设备数据: %s", device_data)
    except Exception as err:
        _LOGGER.error("加载存储数据时出错: %s", err)
    
    # 确保last_date是datetime.date对象
    if isinstance(device_data["last_date"], str):
        device_data["last_date"] = datetime.strptime(
            device_data["last_date"],
            "%Y-%m-%d"
        ).date()
    
    unique_id = f"{entry.entry_id}_status"
    entity_id = f"binary_sensor.{device_name.lower().replace(' ', '_')}_status"
    
    async def async_update_data():
        """Fetch data from API endpoint."""
        return await update_device_data(device_data, host, store, entry.entry_id)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"device_{device_name}",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
    )

    # 立即获取第一次数据
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