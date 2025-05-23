"""Sensor platform for your_integration."""

from homeassistant.components.sensor import SensorEntity
import aiohttp
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, COORDINATOR, CONF_GAODE_APIKEY
import logging
import math

_LOGGER = logging.getLogger(__name__)

# WGS84转GCJ-02坐标系转换函数
def wgs84_to_gcj02(lon, lat):
    """
    WGS84转GCJ-02坐标系
    代码参考自：https://github.com/wandergis/coordTransform_py
    """
    a = 6378245.0  # 长半轴
    ee = 0.00669342162296594323  # 扁率

    def transform_lat(x, y):
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    def transform_lon(x, y):
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
        return ret

    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    mglat = lat + dlat
    mglon = lon + dlon
    return mglon, mglat

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    gaode_key = config_entry.data.get(CONF_GAODE_APIKEY, "")

    if not gaode_key:
        _LOGGER.warning("未设置高德API密钥，地址传感器将无法工作")
        return

    # 等待coordinator初始化完成
    if not coordinator.data:
        _LOGGER.debug("等待设备数据初始化完成，传感器将在数据可用时创建")
        return
    
    # 检查coordinator有效数据  
    if not isinstance(coordinator.data, list) or len(coordinator.data) == 0:
        _LOGGER.debug("暂无有效设备数据，传感器将在数据可用时创建")
        return
    
    # 为每个设备创建地址传感器和电池传感器
    sensors = []
    for i, device in enumerate(coordinator.data):
        model = device.get("model", "")
        if model:
            # 按照要求格式化设备型号名称
            formatted_model = model.replace(" ", "_").lower()
            sensors.append(DeviceAddressSensor(coordinator, gaode_key, i, formatted_model))
            _LOGGER.info(f"为设备[{model}]创建地址传感器: {formatted_model}_address")
            
            # 创建电池传感器
            sensors.append(DeviceBatterySensor(coordinator, i, formatted_model))
            _LOGGER.info(f"为设备[{model}]创建电池传感器: {formatted_model}_battery")
    
    if sensors:
        async_add_entities(sensors, True)
    else:
        _LOGGER.warning("未能创建任何传感器")

class DeviceAddressSensor(Entity):
    """提供设备位置地址信息的传感器."""

    def __init__(self, coordinator, gaode_key, device_index, device_model):
        """初始化传感器."""
        self._coordinator = coordinator
        self._gaode_key = gaode_key
        self._state = None
        self._device_index = device_index
        self._device_model = device_model
        self._attr_name = f"{device_model}_address"
        self._unique_id = f"{coordinator.data[device_index]['imei']}_address"
        self._icon = "mdi:account"
        self._last_lat = None
        self._last_lon = None
        self._last_update_time = None
        self._attributes = {}

    @property
    def name(self):
        """返回传感器名称."""
        return self._attr_name

    @property
    def unique_id(self):
        """返回传感器唯一ID."""
        return self._unique_id

    @property
    def icon(self):
        """返回传感器图标."""
        return self._icon

    @property
    def state(self):
        """返回传感器状态（地址）."""
        return self._state
        
    @property
    def extra_state_attributes(self):
        """返回额外属性."""
        return self._attributes

    @property
    def device_info(self):
        """返回设备信息."""
        try:
            return {
                "identifiers": {(DOMAIN, self._coordinator.data[self._device_index]["imei"])},
                "name": self._device_model,
                "manufacturer": "Xiaomi",
                "model": self._device_model
            }
        except (IndexError, KeyError):
            # 如果出现数据不一致的情况，返回基本信息
            return {
                "identifiers": {(DOMAIN, self._unique_id.replace("_address", ""))},
                "name": self._device_model,
                "manufacturer": "Xiaomi"
            }

    async def async_update(self):
        """手动触发更新."""
        await self._refresh_address()

    async def _refresh_address(self):
        """更新地址信息."""
        # 检查coordinator数据是否有效
        data = self._coordinator.data
        if not isinstance(data, list) or self._device_index >= len(data):
            _LOGGER.error(f"设备[{self._device_model}]没有有效数据，无法更新地址")
            return
        
        device_data = data[self._device_index]
        wgs_lat = device_data.get("device_lat")
        wgs_lon = device_data.get("device_lon")
        location_update_time = device_data.get("device_location_update_time")
        
        # 更新传感器属性
        self._attributes = {
            "last_update": location_update_time or "未知",
            "coordinate_type": device_data.get("coordinate_type", "未知"),
            "device_status": device_data.get("device_status", "未知"),
            "device_power": device_data.get("device_power", "未知")
        }
        
        # 检查位置更新时间是否变化
        if location_update_time == self._last_update_time and self._state:
            return
            
        # 检查是否有坐标
        if not (wgs_lat and wgs_lon and self._gaode_key):
            _LOGGER.warning(f"设备[{self._device_model}]缺少坐标或API密钥，无法获取新地址")
            
            # 如果已有历史地址，保留该地址
            if self._state and self._state not in ["无法获取位置", "地址获取异常", "高德API返回错误", "高德API请求失败", "地址解析失败", "坐标格式错误"]:
                pass
            else:
                self._state = "等待位置数据"
            return

        try:
            # 转换坐标（WGS84转GCJ02，高德API使用GCJ02坐标系）
            gcj_lon, gcj_lat = wgs84_to_gcj02(float(wgs_lon), float(wgs_lat))
            
            # 保存当前坐标用于比较
            self._last_lat = wgs_lat
            self._last_lon = wgs_lon
            self._last_update_time = location_update_time
            
            # 构建高德逆地理编码API请求
            url = "https://restapi.amap.com/v3/geocode/regeo"
            params = {
                "location": f"{gcj_lon},{gcj_lat}", 
                "key": self._gaode_key,
                "radius": 1000,  # 搜索半径
                "extensions": "base"  # 返回基本信息
            }

            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        js = await resp.json()
                        if js.get("status") == "1":  # 1表示成功
                            address = js.get("regeocode", {}).get("formatted_address")
                            if address:
                                self._state = address
                            else:
                                self._state = "地址解析失败"
                                _LOGGER.warning(f"设备[{self._device_model}]地址解析失败，API返回数据不包含地址")
                        else:
                            self._state = "高德API返回错误"
                            _LOGGER.warning(f"高德API返回错误，状态码: {js.get('status')}, 信息: {js.get('info')}")
                    else:
                        self._state = f"高德API请求失败({resp.status})"
                        _LOGGER.warning(f"高德API请求失败，HTTP状态码: {resp.status}")
        except ValueError as e:
            self._state = "坐标格式错误"
            _LOGGER.error(f"坐标格式错误: {e}")
        except Exception as ex:
            self._state = "地址获取异常"
            _LOGGER.exception(f"获取地址时发生异常: {ex}")

    async def async_added_to_hass(self):
        """当传感器添加到Home Assistant时初始化."""
        # 注册回调函数，在coordinator数据更新时调用
        async def update_address(*_):
            """当坐标变化时更新地址."""
            await self._refresh_address()
            self.async_write_ha_state()
            
        self.async_on_remove(
            self._coordinator.async_add_listener(update_address)
        )
        
        # 初始获取地址
        await self._refresh_address()

    async def async_will_remove_from_hass(self):
        """Cleanup."""
        # 监听器清理由async_on_remove处理

class DeviceBatterySensor(Entity):
    """提供设备电池电量信息的传感器."""

    def __init__(self, coordinator, device_index, device_model):
        """初始化传感器."""
        self._coordinator = coordinator
        self._state = None
        self._device_index = device_index
        self._device_model = device_model
        self._attr_name = f"{device_model}_battery"
        self._unique_id = f"{coordinator.data[device_index]['imei']}_battery"
        self._icon = "mdi:battery"
        self._attributes = {}

    @property
    def name(self):
        """返回传感器名称."""
        return self._attr_name

    @property
    def unique_id(self):
        """返回传感器唯一ID."""
        return self._unique_id

    @property
    def icon(self):
        """返回传感器图标，根据电量值动态变化."""
        if self._state is None:
            return "mdi:battery-unknown"
            
        try:
            battery_level = int(self._state)
            if battery_level <= 10:
                return "mdi:battery-10"
            elif battery_level <= 20:
                return "mdi:battery-20"
            elif battery_level <= 30:
                return "mdi:battery-30"
            elif battery_level <= 40:
                return "mdi:battery-40"
            elif battery_level <= 50:
                return "mdi:battery-50"
            elif battery_level <= 60:
                return "mdi:battery-60"
            elif battery_level <= 70:
                return "mdi:battery-70"
            elif battery_level <= 80:
                return "mdi:battery-80"
            elif battery_level <= 90:
                return "mdi:battery-90"
            return "mdi:battery"
        except (ValueError, TypeError):
            return "mdi:battery-unknown"

    @property
    def state(self):
        """返回传感器状态（电池电量）."""
        return self._state
        
    @property
    def unit_of_measurement(self):
        """返回测量单位."""
        return "%"
        
    @property
    def device_class(self):
        """返回设备类."""
        return "battery"

    @property
    def extra_state_attributes(self):
        """返回额外属性."""
        return self._attributes

    @property
    def device_info(self):
        """返回设备信息."""
        try:
            return {
                "identifiers": {(DOMAIN, self._coordinator.data[self._device_index]["imei"])},
                "name": self._device_model,
                "manufacturer": "Xiaomi",
                "model": self._device_model
            }
        except (IndexError, KeyError):
            # 如果出现数据不一致的情况，返回基本信息
            return {
                "identifiers": {(DOMAIN, self._unique_id.replace("_battery", ""))},
                "name": self._device_model,
                "manufacturer": "Xiaomi"
            }

    async def async_update(self):
        """手动触发更新."""
        await self._refresh_battery()

    async def _refresh_battery(self):
        """更新电池电量信息."""
        try:
            # 检查coordinator数据是否有效
            data = self._coordinator.data
            if not isinstance(data, list) or self._device_index >= len(data):
                _LOGGER.error(f"设备[{self._device_model}]没有有效数据，无法更新电池电量")
                return
            
            device_data = data[self._device_index]
            battery_level = device_data.get("device_power")
            
            # 更新电池电量
            if battery_level is not None:
                self._state = battery_level
            else:
                _LOGGER.error(f"设备[{self._device_model}]没有电池电量数据")
                self._state = None
        except Exception as e:
            _LOGGER.error(f"更新设备[{self._device_model}]电池电量时发生错误: {str(e)}")
            self._state = None

    async def async_added_to_hass(self):
        """当传感器添加到Home Assistant时初始化."""
        # 注册回调函数，在coordinator数据更新时调用
        async def update_battery(*_):
            """当电池电量变化时更新."""
            await self._refresh_battery()
            self.async_write_ha_state()
            
        self.async_on_remove(
            self._coordinator.async_add_listener(update_battery)
        )
        
        # 初始获取电池电量
        await self._refresh_battery()
