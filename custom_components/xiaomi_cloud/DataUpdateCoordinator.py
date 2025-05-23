import asyncio
import json
import datetime
import time
import logging
import re
import base64
import hashlib
import math
from urllib import parse
import aiohttp
import async_timeout
from aiohttp.client_exceptions import ClientConnectorError
from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.components.device_tracker import (
    ATTR_BATTERY,
    DOMAIN as DEVICE_TRACKER,
)
from homeassistant.util.dt import as_local, now, utcnow, parse_datetime

from .const import (
    DOMAIN,
)
_LOGGER = logging.getLogger(__name__)

class XiaomiCloudDataUpdateCoordinator(DataUpdateCoordinator):
    """小米云服务数据更新协调器."""
    def __init__(self, hass, user, password, scan_interval, coordinate_type, gaode_api_key=None, 
                 low_battery_polling=False, low_battery_threshold=40, low_battery_interval=10):
        """初始化协调器."""
        self._username = user
        self._password = password
        self._headers = {}
        self._cookies = {}
        self._device_info = {}
        self._serviceLoginAuth2_json = {}
        self._sign = None
        self._scan_interval = int(scan_interval)  # 确保转换为整数并存储
        self._coordinate_type = coordinate_type
        self._gaode_api_key = gaode_api_key
        # 低电量相关设置
        self._low_battery_polling = low_battery_polling
        self._low_battery_threshold = int(low_battery_threshold)  # 低电量阈值
        self._low_battery_interval = int(low_battery_interval)  # 低电量时更新间隔
        self._normal_scan_interval = int(scan_interval)  # 保存正常更新间隔
        self._is_low_battery_mode = False  # 是否处于低电量模式
        
        self.service_data = None
        self.userId = None
        self.login_result = False
        self.service = None
        self._last_position_update = {}  # 记录每个设备上次位置更新时间
        self._Service_Token = None  # 确保_Service_Token被初始化
        self._last_devices_data = []  # 存储上次获取的设备数据，用于恢复状态

        # 确保使用正确的更新间隔
        _LOGGER.info("初始化小米云服务 - 位置更新间隔设置为 %s 分钟", self._scan_interval)
        _LOGGER.info("坐标系类型设置为 %s", self._coordinate_type)
        if self._gaode_api_key:
            _LOGGER.info("高德API密钥已配置: %s", self._gaode_api_key)
        else:
            _LOGGER.warning("高德API密钥未配置，可能影响地址解析功能")
            
        if self._low_battery_polling:
            _LOGGER.info("启用低电量快速更新 - 阈值: %s%%, 低电量更新间隔: %s分钟", 
                       self._low_battery_threshold, self._low_battery_interval)
        
        # 设置更新间隔
        update_interval = datetime.timedelta(minutes=self._scan_interval)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)
        
        # 确保初始化后立即调度一次以确保正确应用更新间隔
        hass.async_create_task(self._schedule_initial_refresh())

    async def _get_sign(self, session):
        """获取签名信息."""
        url = 'https://account.xiaomi.com/pass/serviceLogin?sid%3Di.mi.com&sid=i.mi.com&_locale=zh_CN&_snsNone=true'
        pattern = re.compile(r'_sign=(.*?)&')
        _LOGGER.debug("开始获取签名")
        try:
            with async_timeout.timeout(15):
                r = await session.get(url, headers=self._headers)
            self._cookies['pass_trace'] = r.history[0].headers.getall('Set-Cookie')[2].split(";")[0].split("=")[1]
            sign_value = parse.unquote(pattern.findall(r.history[0].headers.getall('Location')[0])[0])
            _LOGGER.debug("获取到签名: %s", sign_value)
            self._sign = sign_value
            return True
        except Exception as e:
            _LOGGER.warning("获取签名时出错: %s", str(e))
            return False

    async def _serviceLoginAuth2(self, session, captCode=None):
        """执行服务登录认证."""
        url = 'https://account.xiaomi.com/pass/serviceLoginAuth2'
        self._headers['Content-Type'] = 'application/x-www-form-urlencoded'
        self._headers['Accept'] = '*/*'
        self._headers['Origin'] = 'https://account.xiaomi.com'
        self._headers['Referer'] = 'https://account.xiaomi.com/pass/serviceLogin?sid%3Di.mi.com&sid=i.mi.com&_locale=zh_CN&_snsNone=true'
        self._headers['Cookie'] = 'pass_trace={};'.format(self._cookies['pass_trace'])

        auth_post_data = {'_json': 'true',
                          '_sign': self._sign,
                          'callback': 'https://i.mi.com/sts',
                          'hash': hashlib.md5(self._password.encode('utf-8')).hexdigest().upper(),
                          'qs': '%3Fsid%253Di.mi.com%26sid%3Di.mi.com%26_locale%3Dzh_CN%26_snsNone%3Dtrue',
                          'serviceParam': '{"checkSafePhone":false}',
                          'sid': 'i.mi.com',
                          'user': self._username}
        try:
            if captCode is not None:
                url = 'https://account.xiaomi.com/pass/serviceLoginAuth2?_dc={}'.format(
                    int(round(time.time() * 1000)))
                auth_post_data['captCode'] = captCode
                self._headers['Cookie'] = self._headers['Cookie'] + \
                                          '; ick={}'.format(self._cookies['ick'])
            
            _LOGGER.debug("执行服务登录认证")
            with async_timeout.timeout(15):
                r = await session.post(url, headers=self._headers, data=auth_post_data, cookies=self._cookies)
            
            if not r.cookies.get('passToken'):
                _LOGGER.warning("登录认证失败，未获取到passToken")
                return False
                
            self._cookies['pwdToken'] = r.cookies.get('passToken').value
            self._serviceLoginAuth2_json = json.loads((await r.text())[11:])
            _LOGGER.debug("服务登录认证成功")
            return True
        except Exception as e:
            _LOGGER.warning("服务登录认证时出错: %s", str(e))
            return False

    async def _login_miai(self, session):
        """登录小米AI服务."""
        try:
            serviceToken = "nonce={}&{}".format(
                self._serviceLoginAuth2_json['nonce'], self._serviceLoginAuth2_json['ssecurity'])
            serviceToken_sha1 = hashlib.sha1(serviceToken.encode('utf-8')).digest()
            base64_serviceToken = base64.b64encode(serviceToken_sha1)
            loginmiai_header = {'User-Agent': 'MISoundBox/1.4.0,iosPassportSDK/iOS-3.2.7 iOS/11.2.5',
                                'Accept-Language': 'zh-cn', 'Connection': 'keep-alive'}
            url = self._serviceLoginAuth2_json['location'] + \
                  "&clientSign=" + parse.quote(base64_serviceToken.decode())
            
            _LOGGER.debug("开始登录小米AI服务")
            with async_timeout.timeout(15):
                r = await session.get(url, headers=loginmiai_header)
            
            if r.status == 200 and r.cookies.get('serviceToken') and r.cookies.get('userId'):
                self._Service_Token = r.cookies.get('serviceToken').value
                self.userId = r.cookies.get('userId').value
                _LOGGER.debug("登录小米AI服务成功，用户ID: %s", self.userId)
                return True
            else:
                _LOGGER.warning("登录小米AI服务失败，状态码: %s", r.status)
                return False
        except Exception as e:
            _LOGGER.warning("登录小米AI服务时出错: %s", str(e))
            return False

    async def _get_device_info(self, session):
        """获取设备信息."""
        url = 'https://i.mi.com/find/device/full/status?ts={}'.format(
            int(round(time.time() * 1000)))
        get_device_list_header = {'Cookie': 'userId={};serviceToken={}'.format(
            self.userId, self._Service_Token)}
        try:
            _LOGGER.debug("开始获取设备信息")
            with async_timeout.timeout(15):
                r = await session.get(url, headers=get_device_list_header)
            
            # 检查HTTP状态码
            if r.status == 401:
                _LOGGER.warning("获取设备信息时登录失效(401)，需要重新登录")
                self.login_result = False
                return False
                
            if r.status == 200:
                response_data = json.loads(await r.text())
                
                # 检查API返回的错误码
                if isinstance(response_data, dict) and response_data.get('code') in [401, 6]:
                    _LOGGER.warning("获取设备信息API返回登录失效错误码(%s)，需要重新登录", response_data.get('code'))
                    self.login_result = False
                    return False
                
                if 'data' not in response_data or 'devices' not in response_data['data']:
                    _LOGGER.warning("设备信息数据格式异常，未找到设备列表")
                    return False
                    
                device_count = len(response_data['data']['devices'])
                _LOGGER.debug('获取到%d个设备信息', device_count)
                data = response_data['data']['devices']

                self._device_info = data
                return True
            else:
                _LOGGER.warning("获取设备信息失败，HTTP状态码: %s", r.status)
                self.login_result = False
                return False
        except Exception as e:
            _LOGGER.warning("获取设备信息时出错: %s", str(e))
            return False
    
    async def _send_find_device_command(self, session:aiohttp.ClientSession):
        """发送查找设备命令，触发手机定位."""
        if not self._device_info:
            _LOGGER.warning("没有设备信息，无法发送查找命令")
            return False
            
        flag = True
        device_count = len(self._device_info)
        _LOGGER.info("开始向%d个设备发送查找命令", device_count)
        
        for vin in self._device_info:
            imei = vin.get("imei")
            model = vin.get("model", "未知设备")
            
            if not imei:
                _LOGGER.warning(f"设备[{model}]没有IMEI，跳过")
                continue
                
            url = 'https://i.mi.com/find/device/{}/location'.format(imei)
            _send_find_device_command_header = {
                'Cookie': 'userId={};serviceToken={}'.format(self.userId, self._Service_Token)}
            data = {'userId': self.userId, 'imei': imei,
                    'auto': 'false', 'channel': 'web', 'serviceToken': self._Service_Token}
            try:
                _LOGGER.info(f"向设备[{model}]发送查找命令，触发定位...")
                with async_timeout.timeout(15):
                    r = await session.post(url, headers=_send_find_device_command_header, data=data)
                
                if r.status != 200:
                    _LOGGER.warning(f"查找设备[{model}]失败，HTTP状态码: {r.status}")
                    if r.status == 401:
                        self.login_result = False
                        flag = False
                        break
                    continue
                
                try:
                    response_json = await r.json()
                    
                    # 检查返回状态和状态码，处理登录失效的情况
                    if isinstance(response_json, dict) and response_json.get('code') in [401, 6]:
                        _LOGGER.warning(f"查找设备[{model}]时登录失效(401)，需要重新登录")
                        self.login_result = False
                        flag = False
                        break
                    _LOGGER.info(f"成功发送查找命令到设备[{model}]")
                except Exception as e:
                    _LOGGER.warning(f"解析查找设备[{model}]响应时出错: {str(e)}")
            except Exception as e:
                _LOGGER.warning(f"向设备[{model}]发送查找命令时出错: {str(e)}")
                self.login_result = False
                flag = False
        
        _LOGGER.info("发送查找命令完成，结果: %s", "成功" if flag else "失败")
        return flag
    
    async def _send_noise_command(self, session:aiohttp.ClientSession):
        """发送播放声音命令."""
        if not self.service_data or 'imei' not in self.service_data:
            _LOGGER.warning("没有指定设备IMEI，无法发送声音命令")
            return False
            
        flag = True
        imei = self.service_data['imei']  
        url = 'https://i.mi.com/find/device/{}/noise'.format(imei)
        _send_noise_command_header = {
            'Cookie': 'userId={};serviceToken={}'.format(self.userId, self._Service_Token)}
        data = {'userId': self.userId, 'imei': imei,
                'auto': 'false', 'channel': 'web', 'serviceToken': self._Service_Token}
        try:
            _LOGGER.info("向设备[%s]发送播放声音命令", imei)
            with async_timeout.timeout(15):
                r = await session.post(url, headers=_send_noise_command_header, data=data)
            
            if r.status != 200:
                _LOGGER.warning("发送声音命令失败，HTTP状态码: %s", r.status)
                self.login_result = False
                return False
                
            response_json = await r.json()
            _LOGGER.debug("声音命令响应: %s", response_json)
            
            # 检查返回状态和状态码，处理登录失效的情况
            if isinstance(response_json, dict) and response_json.get('code') in [401, 6]:
                _LOGGER.warning("发送声音指令时登录失效(401)，需要重新登录")
                self.login_result = False
                flag = False
            else:
                _LOGGER.info("成功发送声音命令到设备[%s]", imei)
                self.service = None
                self.service_data = None
            
            return flag
        except Exception as e:
            _LOGGER.warning("发送声音命令时出错: %s", str(e))
            self.login_result = False
            return False

    async def _send_lost_command(self, session:aiohttp.ClientSession):
        """发送设备丢失命令."""
        if not self.service_data or 'imei' not in self.service_data:
            _LOGGER.warning("没有指定设备IMEI，无法发送丢失命令")
            return False
        
        flag = True
        imei = self.service_data['imei']  
        content = self.service_data.get('content', "")  
        phone = self.service_data.get('phone', "")  
        message = {"content": content, "phone": phone}
        onlinenotify = self.service_data.get('onlinenotify', True)
        url = 'https://i.mi.com/find/device/{}/lost'.format(imei)
        _send_lost_command_header = {
            'Cookie': 'userId={};serviceToken={}'.format(self.userId, self._Service_Token)}
        data = {'userId': self.userId, 'imei': imei,
                'deleteCard': 'false', 'channel': 'web', 'serviceToken': self._Service_Token, 
                'onlineNotify': onlinenotify, 'message': json.dumps(message)}
        try:
            _LOGGER.info("向设备[%s]发送丢失命令", imei)
            with async_timeout.timeout(15):
                r = await session.post(url, headers=_send_lost_command_header, data=data)
            
            if r.status != 200:
                _LOGGER.warning("发送丢失命令失败，HTTP状态码: %s", r.status)
                self.login_result = False
                return False
                
            response_json = await r.json()
            _LOGGER.debug("丢失命令响应: %s", response_json)
            
            if isinstance(response_json, dict) and response_json.get('code') in [401, 6]:
                _LOGGER.warning("发送丢失指令时登录失效(401)，需要重新登录")
                self.login_result = False
                flag = False
            else:
                _LOGGER.info("成功发送丢失命令到设备[%s]", imei)
                self.service = None
                self.service_data = None
            
            return flag
        except Exception as e:
            _LOGGER.warning("发送丢失命令时出错: %s", str(e))
            self.login_result = False
            return False

    async def _send_clipboard_command(self, session:aiohttp.ClientSession):
        """发送剪贴板命令."""
        if not self.service_data or 'text' not in self.service_data:
            _LOGGER.warning("没有指定文本内容，无法发送剪贴板命令")
            return False
            
        flag = True
        text = self.service_data['text']  
        url = 'https://i.mi.com/clipboard/lite/text'
        _send_clipboard_command_header = {
            'Cookie': 'userId={};serviceToken={}'.format(self.userId, self._Service_Token)}
        data = {'text': text, 'serviceToken': self._Service_Token}
        try:
            _LOGGER.info("发送剪贴板命令，文本内容长度: %d", len(text))
            with async_timeout.timeout(15):
                r = await session.post(url, headers=_send_clipboard_command_header, data=data)
            
            if r.status != 200:
                _LOGGER.warning("发送剪贴板命令失败，HTTP状态码: %s", r.status)
                self.login_result = False
                return False
                
            response_json = await r.json()
            _LOGGER.debug("剪贴板命令响应: %s", response_json)
            
            if isinstance(response_json, dict) and response_json.get('code') in [401, 6]:
                _LOGGER.warning("发送剪贴板指令时登录失效(401)，需要重新登录")
                self.login_result = False
                flag = False
            else:
                _LOGGER.info("成功发送剪贴板命令")
                self.service = None
                self.service_data = None
            
            return flag
        except Exception as e:
            _LOGGER.warning("发送剪贴板命令时出错: %s", str(e))
            self.login_result = False
            return False
  
    async def _send_command(self, data):
        """发送命令入口."""
        if not data or 'service' not in data or 'data' not in data:
            _LOGGER.warning("命令数据格式不正确，无法发送命令")
            return
            
        self.service_data = data['data']
        self.service = data['service']
        _LOGGER.info("准备发送命令: %s", self.service)
        await self.async_refresh()

    async def _get_device_location(self, session:aiohttp.ClientSession):
        """获取设备位置信息."""
        if not self._device_info:
            _LOGGER.warning("没有设备信息，无法获取位置")
            return []
            
        devices_info = []
        device_count = len(self._device_info)
        _LOGGER.info("开始获取%d个设备的位置信息", device_count)
        
        for vin in self._device_info:
            imei = vin.get("imei") 
            model = vin.get("model", "未知设备") 
            version = vin.get("version", "未知版本")
            
            if not imei:
                _LOGGER.warning(f"设备[{model}]没有IMEI，跳过获取位置")
                continue
                
            url = 'https://i.mi.com/find/device/status?ts={}&fid={}'.format(
                int(round(time.time() * 1000)), imei)
            _send_find_device_command_header = {
                'Cookie': 'userId={};serviceToken={}'.format(self.userId, self._Service_Token)}
            try:
                with async_timeout.timeout(15):
                    r = await session.get(url, headers=_send_find_device_command_header)
                
                # 检查HTTP状态码
                if r.status == 401:
                    _LOGGER.warning("获取设备位置时登录失效(401)，需要重新登录")
                    self.login_result = False
                    return []
                
                if r.status != 200:
                    _LOGGER.warning(f"获取设备[{model}]位置失败，HTTP状态码: {r.status}")
                    continue
                    
                response_data = json.loads(await r.text())
                
                # 检查API返回的错误码
                if isinstance(response_data, dict) and response_data.get('code') in [401, 6]:
                    _LOGGER.warning("API返回登录失效错误码(%s)，需要重新登录", response_data.get('code'))
                    self.login_result = False
                    return []
                
                if 'data' not in response_data:
                    _LOGGER.warning(f"设备[{model}]位置数据格式异常，缺少data字段")
                    continue
                
                _LOGGER.debug(f"获取设备[{model}]位置数据成功")

                # 创建设备基本信息字典
                device_info = {
                    "imei": imei,
                    "model": model,
                    "version": version
                }
                
                # 提取电量信息（如果可用）
                if "powerLevel" in response_data['data']:
                    device_info["device_power"] = response_data['data']['powerLevel'].get('value', 0)
                
                # 提取设备状态（开启/关闭）
                if "status" in response_data['data']:
                    device_info["device_status"] = response_data['data']['status']
                
                # 检查是否有位置数据
                location_data_available = False
                position_updated = False
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 检查位置receipt数据是否可用
                if "location" in response_data['data'] and "receipt" in response_data['data']['location']:
                    location_receipt = response_data['data']['location']['receipt']
                    
                    gpsInfoTransformed = location_receipt.get('gpsInfoTransformed', [])
                    
                    # 记录坐标系转换列表
                    if not gpsInfoTransformed:
                        _LOGGER.warning(f"设备[{model}]无可用坐标系转换列表")

                    # 获取位置更新时间
                    if 'infoTime' in location_receipt:
                        info_time_ms = int(location_receipt['infoTime'])
                        time_array = time.localtime(info_time_ms / 1000)
                        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time_array)
                        device_info["device_location_update_time"] = formatted_time
                        
                        # 判断位置是否更新
                        last_update = self._last_position_update.get(imei, 0)
                        if info_time_ms > last_update:
                            self._last_position_update[imei] = info_time_ms
                            position_updated = True
                            _LOGGER.info(f"设备[{model}]位置已更新，时间: {formatted_time}")

                    # 处理GPS坐标
                    if gpsInfoTransformed:
                        location_info_json = None
                        
                        # 根据选择的坐标系类型获取对应的坐标信息
                        if self._coordinate_type == "original" and 'gpsInfo' in location_receipt:
                            location_info_json = location_receipt.get('gpsInfo', {})
                        else:
                            # 在转换列表中查找指定的坐标系
                            for item in gpsInfoTransformed:
                                if item.get('coordinateType') == self._coordinate_type:
                                    location_info_json = item
                                    break
                        
                        # 如果找不到指定坐标系，尝试使用第一个可用的
                        if not location_info_json and gpsInfoTransformed:
                            location_info_json = gpsInfoTransformed[0]
                            _LOGGER.info(f"未找到匹配坐标系 {self._coordinate_type}，使用第一个可用坐标系")
                        
                        if location_info_json:
                            device_info["device_lat"] = location_info_json.get('latitude')
                            device_info["device_lon"] = location_info_json.get('longitude')
                            device_info["device_accuracy"] = int(location_info_json.get('accuracy', 0))
                            device_info["coordinate_type"] = location_info_json.get('coordinateType')
                            location_data_available = True
                        else:
                            _LOGGER.warning(f"设备[{model}]未找到任何坐标系数据")

                        # 添加其他位置数据
                        if 'phone' in location_receipt:
                            device_info["device_phone"] = location_receipt.get('phone', 0)
                
                # 如果没有位置数据，记录日志
                if not location_data_available:
                    _LOGGER.warning(f"设备[{model}]没有位置数据可用，查找设备可能未成功触发")
                
                # 添加设备信息到列表，即使位置数据不完整
                devices_info.append(device_info)
            except Exception as e:
                _LOGGER.error(f"处理设备[{model}]位置时出错: {str(e)}")
        
        # 记录警告如果没有设备数据
        devices_count = len(devices_info)
        if devices_count > 0:
            _LOGGER.info(f"成功获取了{devices_count}个设备的数据")
        else:
            _LOGGER.warning("未能获取任何有效设备数据")
        
        return devices_info

    def GCJ2WGS(self, lon, lat):
        """GCJ-02坐标转WGS-84坐标."""
        if not lon or not lat:
            return [lon, lat]
            
        a = 6378245.0 # 克拉索夫斯基椭球参数长半轴a
        ee = 0.00669342162296594323 #克拉索夫斯基椭球参数第一偏心率平方
        PI = 3.14159265358979324 # 圆周率

        x = lon - 105.0
        y = lat - 35.0

        dLon = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x));
        dLon += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0;
        dLon += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0;
        dLon += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0;

        dLat = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x));
        dLat += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0;
        dLat += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0;
        dLat += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0;
        radLat = lat / 180.0 * PI
        magic = math.sin(radLat)
        magic = 1 - ee * magic * magic
        sqrtMagic = math.sqrt(magic)
        dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * PI);
        dLon = (dLon * 180.0) / (a / sqrtMagic * math.cos(radLat) * PI);
        wgsLon = lon - dLon
        wgsLat = lat - dLat
        return [wgsLon, wgsLat]

    async def _async_update_data(self):
        """更新数据，定时调用."""
        _LOGGER.debug("开始数据更新周期，当前更新间隔为 %s 分钟，服务: %s", self._scan_interval, self.service)
        
        # 获取设备数据
        devices_data = []
        
        try:
            session = async_get_clientsession(self.hass)
            
            # 如果设置了特定服务，优先处理
            if self.service in ["noise", "lost", "clipboard"]:
                if self.login_result is True:
                    _LOGGER.info("执行服务: %s", self.service)
                    if self.service == "noise":
                        service_result = await self._send_noise_command(session)
                    elif self.service == 'lost':
                        service_result = await self._send_lost_command(session)
                    elif self.service == 'clipboard':
                        service_result = await self._send_clipboard_command(session)
                    
                    # 如果服务执行失败可能是登录失效，尝试重新登录
                    if not service_result:
                        _LOGGER.info("服务执行失败，尝试重新登录")
                        self.login_result = False
                else:
                    _LOGGER.info("用户未登录，将在下一步中执行登录")
                        
            # 处理登录状态
            if not self.login_result:
                # 用户未登录或登录失效，执行登录流程
                _LOGGER.info("开始执行登录流程")
                session.cookie_jar.clear()
                
                # 按顺序执行登录步骤
                if not await self._get_sign(session):
                    _LOGGER.warning("获取sign失败")
                    return self._last_devices_data or []
                
                if not await self._serviceLoginAuth2(session):
                    _LOGGER.warning('登录验证失败')
                    return self._last_devices_data or []
                
                if self._serviceLoginAuth2_json.get('code', -1) != 0:
                    _LOGGER.warning('登录验证返回错误码: %s', self._serviceLoginAuth2_json.get('code', -1))
                    return self._last_devices_data or []
                
                # 登录成功，执行miai登录
                if not await self._login_miai(session):
                    _LOGGER.warning('登录小米云失败')
                    return self._last_devices_data or []
                
                if not await self._get_device_info(session):
                    _LOGGER.warning('获取设备信息失败')
                    return self._last_devices_data or []
                
                _LOGGER.info("登录成功，获取到%d个设备信息", len(self._device_info))
                self.login_result = True
                
                # 重新执行原服务请求（如果有）
                if self.service in ["noise", "lost", "clipboard"]:
                    _LOGGER.info("重新尝试执行服务: %s", self.service)
                    if self.service == "noise":
                        await self._send_noise_command(session)
                    elif self.service == 'lost':
                        await self._send_lost_command(session)
                    elif self.service == 'clipboard':
                        await self._send_clipboard_command(session)
            
            # 执行定时查找设备逻辑
            _LOGGER.info("执行定时查找设备操作...")
            find_result = await self._send_find_device_command(session)
            
            # 如果发送查找命令失败且是因为登录问题，尝试重新登录并再次查找
            if not find_result and not self.login_result:
                _LOGGER.info("查找设备失败，尝试重新登录")
                session.cookie_jar.clear()
                
                # 尝试执行完整的登录流程
                login_success = (await self._get_sign(session) and 
                                await self._serviceLoginAuth2(session) and 
                                self._serviceLoginAuth2_json.get('code', -1) == 0 and
                                await self._login_miai(session) and
                                await self._get_device_info(session))
                
                if login_success:
                    self.login_result = True
                    _LOGGER.info("重新登录成功，再次尝试查找设备")
                    find_result = await self._send_find_device_command(session)
                else:
                    _LOGGER.warning("重新登录失败")
            
            _LOGGER.info("查找设备执行结果: %s", "成功" if find_result else "失败")
            
            # 查找命令发送后，等待一段时间让设备响应
            wait_time = 15
            _LOGGER.info(f"等待{wait_time}秒让设备响应定位请求...")
            await asyncio.sleep(wait_time)
            
            # 获取最新位置
            _LOGGER.info("开始获取设备位置数据...")
            location_data = await self._get_device_location(session)
            
            if not location_data:
                _LOGGER.warning("未能获取设备位置数据")
                # 如果是登录原因导致的失败，返回上次的数据
                if not self.login_result:
                    _LOGGER.info("登录状态已失效，返回上次的设备数据")
                    return self._last_devices_data or []
                    
                # 如果不是登录原因，可能是其他原因，创建基本设备信息
                if self._device_info:
                    _LOGGER.info("尝试创建基本设备信息...")
                    basic_devices = []
                    for vin in self._device_info:
                        basic_devices.append({
                            "imei": vin.get("imei", ""),
                            "model": vin.get("model", "未知设备"),
                            "version": vin.get("version", "未知版本"),
                            "device_status": "unknown"
                        })
                    _LOGGER.debug("创建了%d个基本设备信息对象", len(basic_devices))
                    # 保存基本设备数据以便恢复
                    self._last_devices_data = basic_devices
                    return basic_devices
                return self._last_devices_data or []
            else:
                _LOGGER.info(f"获取设备位置成功，返回{len(location_data)}个设备数据")
                # 保存获取到的设备数据
                self._last_devices_data = location_data
                devices_data = location_data

            # 成功获取设备数据后，检查电量并调整轮询频率（如果启用了低电量功能）
            if self._low_battery_polling and devices_data:
                self._check_battery_levels(devices_data)
            
            return devices_data

        except ClientConnectorError as error:
            _LOGGER.error(f"网络连接错误: {error}")
            if self._last_devices_data:
                _LOGGER.info("使用上次获取的设备数据")
                return self._last_devices_data
            raise UpdateFailed(f"网络连接错误: {error}")
        except Exception as e:
            _LOGGER.error(f"更新数据时发生未处理的异常: {str(e)}")
            if self._last_devices_data:
                _LOGGER.info("使用上次获取的设备数据")
                return self._last_devices_data
            raise UpdateFailed(f"未处理的异常: {str(e)}")

    def _check_battery_levels(self, devices_data):
        """检查设备电量并根据需要调整轮询频率."""
        if not self._low_battery_polling:
            return
            
        # 查找任何低于阈值的设备
        low_battery_device = None
        for device in devices_data:
            battery_level = device.get("device_power")
            if battery_level is not None and int(battery_level) < self._low_battery_threshold:
                low_battery_device = device
                break
                
        current_is_low_battery = low_battery_device is not None
        
        # 如果电量状态变化，更新轮询间隔
        if current_is_low_battery != self._is_low_battery_mode:
            self._is_low_battery_mode = current_is_low_battery
            
            if current_is_low_battery:
                # 切换到低电量模式
                _LOGGER.info("检测到设备 [%s] 电量低于 %s%%，切换到低电量更新模式 (%s分钟)",
                           low_battery_device.get("model", "未知设备"),
                           self._low_battery_threshold,
                           self._low_battery_interval)
                self._scan_interval = self._low_battery_interval
            else:
                # 恢复正常模式
                _LOGGER.info("所有设备电量恢复正常，恢复标准更新间隔 (%s分钟)", 
                           self._normal_scan_interval)
                self._scan_interval = self._normal_scan_interval
                
            # 更新协调器更新间隔
            self._update_interval_changed(self._scan_interval)

    async def async_config_entry_first_refresh(self):
        """执行首次刷新，在Home Assistant启动时调用."""
        _LOGGER.info("执行小米云服务首次数据刷新...")
        try:
            await super().async_config_entry_first_refresh()
        except ConfigEntryNotReady as err:
            # 如果有上次的设备数据，先使用它
            if self._last_devices_data:
                _LOGGER.warning("首次刷新失败，但使用缓存数据保持实体可用: %s", err)
                self.data = self._last_devices_data
                # 设置一个短暂的重试间隔
                asyncio.create_task(self._schedule_refresh_retry())
                return
            raise
            
    async def _schedule_refresh_retry(self):
        """在短暂延迟后尝试重新刷新数据."""
        await asyncio.sleep(60)  # 等待60秒
        _LOGGER.info("尝试重新刷新小米云服务数据...")
        await self.async_refresh()

    async def _update_interval_changed(self, new_interval):
        """更新间隔时间发生变化时处理."""
        try:
            new_interval = int(new_interval)  # 确保转换为整数
            if new_interval != self._scan_interval:
                old_interval = self._scan_interval
                self._scan_interval = new_interval
                _LOGGER.info("位置更新间隔已从 %s 分钟更改为 %s 分钟", old_interval, new_interval)
                
                # 更新协调器的更新间隔
                self.update_interval = datetime.timedelta(minutes=self._scan_interval)
                
                # 取消现有的刷新计划并重新安排
                self._schedule_refresh()
                
                # 可选：立即触发一次刷新以应用新设置
                await self.async_refresh()
                
                return True
            _LOGGER.debug("更新间隔未变化，仍为 %s 分钟", self._scan_interval)
            return False
        except Exception as e:
            _LOGGER.error("更新间隔设置失败: %s", str(e))
            return False
        
    def _schedule_refresh(self):
        """重新安排下一次刷新."""
        if self._unsub_refresh:
            self._unsub_refresh()
            
        self._unsub_refresh = async_track_point_in_utc_time(
            self.hass,
            self._handle_refresh_interval,
            utcnow() + self.update_interval
        )
        _LOGGER.info("已重新安排刷新时间，下次将在 %s 分钟后执行", self._scan_interval)

    async def _schedule_initial_refresh(self):
        """在初始化后立即调度一次以确保正确应用更新间隔."""
        await self.async_refresh()
