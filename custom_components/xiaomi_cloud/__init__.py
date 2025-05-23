"""
小米云服务集成组件。

更多详情请参考:
https://github.com/MagicStarTrace/xiaomi-cloud
"""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.device_tracker import (
    ATTR_BATTERY,
    DOMAIN as DEVICE_TRACKER,
)
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN

from .DataUpdateCoordinator import XiaomiCloudDataUpdateCoordinator

from .const import (
    DOMAIN,
    UNDO_UPDATE_LISTENER,
    COORDINATOR,
    CONF_COORDINATE_TYPE,
    CONF_COORDINATE_TYPE_BAIDU,
    CONF_COORDINATE_TYPE_ORIGINAL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_GAODE_APIKEY,
    CONF_LOW_BATTERY_POLLING,
    DEFAULT_LOW_BATTERY_POLLING,
    CONF_LOW_BATTERY_THRESHOLD,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    CONF_LOW_BATTERY_INTERVAL,
    DEFAULT_LOW_BATTERY_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """设置配置好的小米云服务."""
    hass.data[DOMAIN] = {"devices": set(), "unsub_device_tracker": {}}
    return True

async def async_setup_entry(hass, config_entry) -> bool:
    """设置小米云服务作为配置入口."""
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    
    # 从options或data中获取配置参数
    coordinate_type = config_entry.options.get(
        CONF_COORDINATE_TYPE, 
        config_entry.data.get(CONF_COORDINATE_TYPE, CONF_COORDINATE_TYPE_ORIGINAL)
    )
    
    # 优先从options中获取update_interval，如果没有再从data中获取
    update_interval = config_entry.options.get(
        CONF_UPDATE_INTERVAL, 
        config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )
    
    # 优先从options中获取gaode_api_key，如果没有再从data中获取
    gaode_api_key = config_entry.options.get(
        CONF_GAODE_APIKEY,
        config_entry.data.get(CONF_GAODE_APIKEY, "")
    )
    
    # 获取低电量轮询相关设置
    low_battery_polling = config_entry.options.get(
        CONF_LOW_BATTERY_POLLING,
        config_entry.data.get(CONF_LOW_BATTERY_POLLING, DEFAULT_LOW_BATTERY_POLLING)
    )
    
    low_battery_threshold = config_entry.options.get(
        CONF_LOW_BATTERY_THRESHOLD,
        config_entry.data.get(CONF_LOW_BATTERY_THRESHOLD, DEFAULT_LOW_BATTERY_THRESHOLD)
    )
    
    low_battery_interval = config_entry.options.get(
        CONF_LOW_BATTERY_INTERVAL,
        config_entry.data.get(CONF_LOW_BATTERY_INTERVAL, DEFAULT_LOW_BATTERY_INTERVAL)
    )

    _LOGGER.info("初始化小米云服务...")
    _LOGGER.info("用户名: %s", username)
    _LOGGER.info("位置更新间隔: %s 分钟", update_interval)
    _LOGGER.info("坐标系类型: %s", coordinate_type)
    _LOGGER.info("高德API密钥: %s", gaode_api_key if gaode_api_key != "" else "未设置")
    if low_battery_polling:
        _LOGGER.info("低电量快速更新已启用 - 阈值: %s%%, 更新间隔: %s分钟", 
                   low_battery_threshold, low_battery_interval)

    # 创建数据更新协调器
    coordinator = XiaomiCloudDataUpdateCoordinator(
        hass, username, password, update_interval, coordinate_type, gaode_api_key,
        low_battery_polling, low_battery_threshold, low_battery_interval
    )
    
    # 初始刷新数据
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("无法从小米云服务获取数据，请检查网络连接和账号信息")

    # 设置配置更新监听器
    undo_listener = config_entry.add_update_listener(update_listener)
    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    # 设置平台
    await hass.config_entries.async_forward_entry_setups(
        config_entry, [DEVICE_TRACKER, SENSOR_DOMAIN]
    )

    # 注册服务
    async def services(call):
        """处理服务调用."""
        imei = call.data.get("imei")
        service = call.service
        
        if service == "noise":
            _LOGGER.info("执行播放提示音服务，设备IMEI: %s", imei)
            await coordinator._send_command({'service':'noise','data':{'imei':imei}})
        elif service == "find":
            _LOGGER.info("执行查找设备服务，设备IMEI: %s", imei)
            await coordinator._send_command({'service':'find','data':{'imei':imei}})
        elif service == "lost":
            content = call.data.get("content", "")
            phone = call.data.get("phone", "")
            onlinenotify = call.data.get("onlinenotify", True)
            _LOGGER.info("执行设备丢失服务，设备IMEI: %s", imei)
            await coordinator._send_command({
                'service':'lost',
                'data':{
                    'imei':imei,
                    'content':content,
                    'phone':phone,
                    'onlinenotify':onlinenotify
                }})
        elif service == "clipboard":
            text = call.data.get("text", "")
            _LOGGER.info("执行剪贴板服务，文本内容: %s", text)
            await coordinator._send_command({'service':'clipboard','data':{'text':text}})

    # 注册服务
    hass.services.async_register(DOMAIN, "noise", services)
    hass.services.async_register(DOMAIN, "find", services)
    hass.services.async_register(DOMAIN, "lost", services)
    hass.services.async_register(DOMAIN, "clipboard", services)

    _LOGGER.info("小米云服务设置完成")
    return True

async def async_unload_entry(hass, config_entry):
    """卸载配置入口."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(config_entry, DEVICE_TRACKER)

    # 取消更新监听器
    hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER]()

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok

async def update_listener(hass, config_entry):
    """配置更新监听器."""
    try:
        # 记录配置更改信息
        _LOGGER.info("检测到配置更改，准备更新小米云服务...")
        
        # 获取当前coordinator实例
        coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
        
        # 检查更新间隔是否变更
        old_update_interval = coordinator._scan_interval
        new_update_interval = config_entry.options.get(
            CONF_UPDATE_INTERVAL, 
            config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        
        # 确保转换为整数
        try:
            new_update_interval = int(new_update_interval)
        except (ValueError, TypeError):
            _LOGGER.warning("更新间隔必须为整数，将使用默认值: %s", DEFAULT_UPDATE_INTERVAL)
            new_update_interval = DEFAULT_UPDATE_INTERVAL
        
        # 检查坐标类型是否变更
        old_coordinate_type = coordinator._coordinate_type
        new_coordinate_type = config_entry.options.get(
            CONF_COORDINATE_TYPE, 
            config_entry.data.get(CONF_COORDINATE_TYPE, CONF_COORDINATE_TYPE_ORIGINAL)
        )
        
        # 检查低电量相关配置是否变更
        old_low_battery_polling = coordinator._low_battery_polling
        new_low_battery_polling = config_entry.options.get(
            CONF_LOW_BATTERY_POLLING,
            config_entry.data.get(CONF_LOW_BATTERY_POLLING, DEFAULT_LOW_BATTERY_POLLING)
        )
        
        old_low_battery_threshold = coordinator._low_battery_threshold
        new_low_battery_threshold = config_entry.options.get(
            CONF_LOW_BATTERY_THRESHOLD,
            config_entry.data.get(CONF_LOW_BATTERY_THRESHOLD, DEFAULT_LOW_BATTERY_THRESHOLD)
        )
        
        old_low_battery_interval = coordinator._low_battery_interval
        new_low_battery_interval = config_entry.options.get(
            CONF_LOW_BATTERY_INTERVAL,
            config_entry.data.get(CONF_LOW_BATTERY_INTERVAL, DEFAULT_LOW_BATTERY_INTERVAL)
        )
        
        # 记录配置变更
        config_changed = False
        
        if old_update_interval != new_update_interval:
            _LOGGER.info("位置更新间隔已从 %s 分钟更改为 %s 分钟", old_update_interval, new_update_interval)
            # 更新normal_scan_interval
            coordinator._normal_scan_interval = new_update_interval
            # 如果不处于低电量模式，更新当前间隔
            if not coordinator._is_low_battery_mode:
                await coordinator._update_interval_changed(new_update_interval)
            config_changed = True
            
        if old_coordinate_type != new_coordinate_type:
            _LOGGER.info("坐标系类型已从 %s 更改为 %s", old_coordinate_type, new_coordinate_type)
            coordinator._coordinate_type = new_coordinate_type
            config_changed = True
        
        # 检查高德API密钥是否变更
        old_gaode_api_key = coordinator._gaode_api_key
        new_gaode_api_key = config_entry.options.get(
            CONF_GAODE_APIKEY,
            config_entry.data.get(CONF_GAODE_APIKEY, "")
        )
        
        if old_gaode_api_key != new_gaode_api_key:
            _LOGGER.info("高德API密钥已更改")
            coordinator._gaode_api_key = new_gaode_api_key
            config_changed = True
            
        # 处理低电量相关设置变更
        low_battery_config_changed = False
        
        if old_low_battery_polling != new_low_battery_polling:
            _LOGGER.info("低电量快速更新设置已从 %s 更改为 %s", 
                       "启用" if old_low_battery_polling else "禁用", 
                       "启用" if new_low_battery_polling else "禁用")
            coordinator._low_battery_polling = new_low_battery_polling
            low_battery_config_changed = True
            config_changed = True
            
        if old_low_battery_threshold != new_low_battery_threshold:
            _LOGGER.info("低电量阈值已从 %s%% 更改为 %s%%", 
                       old_low_battery_threshold, new_low_battery_threshold)
            coordinator._low_battery_threshold = int(new_low_battery_threshold)
            low_battery_config_changed = True
            config_changed = True
            
        if old_low_battery_interval != new_low_battery_interval:
            _LOGGER.info("低电量更新间隔已从 %s 分钟更改为 %s 分钟", 
                       old_low_battery_interval, new_low_battery_interval)
            coordinator._low_battery_interval = int(new_low_battery_interval)
            low_battery_config_changed = True
            config_changed = True
            
        # 如果低电量配置改变且设备处于低电量模式，需要立即应用新的低电量更新间隔
        if low_battery_config_changed and coordinator._is_low_battery_mode:
            _LOGGER.info("低电量设置已更改，重新应用低电量更新间隔")
            await coordinator._update_interval_changed(coordinator._low_battery_interval)
        
        # 如果有配置变更，立即刷新数据
        if config_changed:
            _LOGGER.info("配置已更改，立即刷新数据...")
            await coordinator.async_refresh()
            _LOGGER.info("小米云服务配置已更新")
        else:
            _LOGGER.info("没有检测到配置变更")
        
        # 仍然重新加载配置入口，以确保其他依赖关系正常
        await hass.config_entries.async_reload(config_entry.entry_id)
        _LOGGER.info("小米云服务配置已重新加载完成")
    except Exception as e:
        _LOGGER.error("更新配置时出错: %s", str(e))

