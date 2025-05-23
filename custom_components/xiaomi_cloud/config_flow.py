"""小米云集成配置流程."""

import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from .const import (
    DOMAIN, 
    CONF_GAODE_APIKEY, 
    CONF_UPDATE_INTERVAL, 
    DEFAULT_UPDATE_INTERVAL,
    CONF_COORDINATE_TYPE,
    CONF_COORDINATE_TYPE_ORIGINAL,
    CONF_COORDINATE_TYPE_GOOGLE,
    CONF_COORDINATE_TYPE_BAIDU,
    CONF_LOW_BATTERY_POLLING,
    DEFAULT_LOW_BATTERY_POLLING,
    CONF_LOW_BATTERY_THRESHOLD,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    CONF_LOW_BATTERY_INTERVAL,
    DEFAULT_LOW_BATTERY_INTERVAL
)

class XiaomiCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """小米云集成配置流程."""
    VERSION = 1
    
    @staticmethod
    def async_get_options_flow(config_entry):
        """获取选项流."""
        return XiaomiCloudOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """处理初始设置步骤."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"小米云服务-{user_input['username']}",
                data={
                    "username": user_input["username"],
                    "password": user_input["password"],
                    CONF_GAODE_APIKEY: user_input.get("高德API密钥", ""),
                    CONF_UPDATE_INTERVAL: user_input.get("位置更新间隔 (分钟)", DEFAULT_UPDATE_INTERVAL),
                    CONF_COORDINATE_TYPE: user_input.get(CONF_COORDINATE_TYPE, CONF_COORDINATE_TYPE_ORIGINAL),
                    CONF_LOW_BATTERY_POLLING: user_input.get("启用低电量快速更新", DEFAULT_LOW_BATTERY_POLLING),
                    CONF_LOW_BATTERY_THRESHOLD: user_input.get("低电量阈值 (%)", DEFAULT_LOW_BATTERY_THRESHOLD),
                    CONF_LOW_BATTERY_INTERVAL: user_input.get("低电量更新间隔 (分钟)", DEFAULT_LOW_BATTERY_INTERVAL),
                },
            )

        # 定义首次配置表单
        coordinate_types = {
            CONF_COORDINATE_TYPE_ORIGINAL: "原始坐标",
            CONF_COORDINATE_TYPE_GOOGLE: "谷歌坐标",
            CONF_COORDINATE_TYPE_BAIDU: "百度坐标"
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                    vol.Optional("高德API密钥", default=""): str,
                    vol.Optional("位置更新间隔 (分钟)", default=DEFAULT_UPDATE_INTERVAL): cv.positive_int,
                    vol.Optional(CONF_COORDINATE_TYPE, default=CONF_COORDINATE_TYPE_ORIGINAL): vol.In(coordinate_types),
                    vol.Optional("启用低电量快速更新", default=DEFAULT_LOW_BATTERY_POLLING): cv.boolean,
                    vol.Optional("低电量阈值 (%)", default=DEFAULT_LOW_BATTERY_THRESHOLD): cv.positive_int,
                    vol.Optional("低电量更新间隔 (分钟)", default=DEFAULT_LOW_BATTERY_INTERVAL): cv.positive_int,
                }
            ),
            errors=errors,
        )

class XiaomiCloudOptionsFlow(config_entries.OptionsFlow):
    """处理小米云选项."""

    def __init__(self, config_entry):
        """初始化选项流."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """管理选项."""
        if user_input is not None:
            return self.async_create_entry(
                title="", 
                data={
                    CONF_GAODE_APIKEY: user_input.get("高德API密钥"),
                    CONF_UPDATE_INTERVAL: user_input.get("位置更新间隔 (分钟)"),
                    CONF_COORDINATE_TYPE: user_input.get(CONF_COORDINATE_TYPE),
                    CONF_LOW_BATTERY_POLLING: user_input.get("启用低电量快速更新"),
                    CONF_LOW_BATTERY_THRESHOLD: user_input.get("低电量阈值 (%)"),
                    CONF_LOW_BATTERY_INTERVAL: user_input.get("低电量更新间隔 (分钟)"),
                }
            )

        # 获取当前值，优先从options中获取，如果没有则从data中获取，再没有则使用默认值
        gaode_api_key = self._config_entry.options.get(
            CONF_GAODE_APIKEY, 
            self._config_entry.data.get(CONF_GAODE_APIKEY, "")
        )
        update_interval = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL, 
            self._config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        coordinate_type = self._config_entry.options.get(
            CONF_COORDINATE_TYPE, 
            self._config_entry.data.get(CONF_COORDINATE_TYPE, CONF_COORDINATE_TYPE_ORIGINAL)
        )
        low_battery_polling = self._config_entry.options.get(
            CONF_LOW_BATTERY_POLLING,
            self._config_entry.data.get(CONF_LOW_BATTERY_POLLING, DEFAULT_LOW_BATTERY_POLLING)
        )
        low_battery_threshold = self._config_entry.options.get(
            CONF_LOW_BATTERY_THRESHOLD,
            self._config_entry.data.get(CONF_LOW_BATTERY_THRESHOLD, DEFAULT_LOW_BATTERY_THRESHOLD)
        )
        low_battery_interval = self._config_entry.options.get(
            CONF_LOW_BATTERY_INTERVAL,
            self._config_entry.data.get(CONF_LOW_BATTERY_INTERVAL, DEFAULT_LOW_BATTERY_INTERVAL)
        )

        # 定义坐标系类型选项
        coordinate_types = {
            CONF_COORDINATE_TYPE_ORIGINAL: "原始坐标",
            CONF_COORDINATE_TYPE_GOOGLE: "谷歌坐标",
            CONF_COORDINATE_TYPE_BAIDU: "百度坐标"
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "高德API密钥", 
                        default=gaode_api_key
                    ): str,
                    vol.Optional(
                        "位置更新间隔 (分钟)", 
                        default=update_interval
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_COORDINATE_TYPE,
                        default=coordinate_type
                    ): vol.In(coordinate_types),
                    vol.Optional(
                        "启用低电量快速更新",
                        default=low_battery_polling
                    ): cv.boolean,
                    vol.Optional(
                        "低电量阈值 (%)",
                        default=low_battery_threshold
                    ): cv.positive_int,
                    vol.Optional(
                        "低电量更新间隔 (分钟)",
                        default=low_battery_interval
                    ): cv.positive_int,
                }
            ),
        )

# 如果有其他步骤或方法，放在这里...
# ... 原有代码 (省略) ... 