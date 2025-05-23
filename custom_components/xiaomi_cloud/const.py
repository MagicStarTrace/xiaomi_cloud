'''
Author        : MagicStarTrace
Github        : https://github.com/MagicStarTrace
Description   : 
Date          : 2025-04-22 20:46:33
LastEditors   : MagicStarTrace
LastEditTime  : 2020-04-22 22:49:23
'''


"""Const file for Xiaomi Cloud."""
CONF_WAKE_ON_START = "enable_wake_on_start"
DOMAIN = "xiaomi_cloud"
COORDINATOR = "coordinator"
DATA_LISTENER = "listener"
UNDO_UPDATE_LISTENER = "undo_update_listener"
DEFAULT_SCAN_INTERVAL = 660
DEFAULT_WAKE_ON_START = False
MIN_SCAN_INTERVAL = 60
SIGNAL_STATE_UPDATED = f"{DOMAIN}.updated"
CONF_COORDINATE_TYPE = "coordinate_type"
CONF_COORDINATE_TYPE_BAIDU = "baidu"
CONF_COORDINATE_TYPE_ORIGINAL = "original"
CONF_COORDINATE_TYPE_GOOGLE = "google"
CONF_GAODE_APIKEY = "gaode_api_key"
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 3  # 默认每3分钟更新一次
CONF_LOW_BATTERY_POLLING = "enable_low_battery_polling"  # 启用低电量快速更新
DEFAULT_LOW_BATTERY_POLLING = False  # 默认不启用
CONF_LOW_BATTERY_THRESHOLD = "low_battery_threshold"  # 低电量阈值
DEFAULT_LOW_BATTERY_THRESHOLD = 40  # 默认40%为低电量
CONF_LOW_BATTERY_INTERVAL = "low_battery_interval"  # 低电量时的更新间隔
DEFAULT_LOW_BATTERY_INTERVAL = 10  # 默认低电量时10分钟更新一次

