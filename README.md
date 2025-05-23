# 小米云集成 (Xiaomi Cloud Integration) for Home Assistant


> Home Assistant自定义组件，用于小米云服务集成

该自定义组件通过连接小米云服务，将您的小米设备坐标地址集成到Home Assistant中。

## 功能特点

- 连接小米云账户（小米/米家）
- 提供支持设备的位置追踪功能
- 从兼容的小米设备获取传感器数据

## GPS定位功能

### 位置追踪细节

本组件利用小米云服务的"查找设备"功能来获取设备的实时位置信息。工作原理如下：

1. **周期性定位更新**：组件每3分钟[默认]自动发送"查找设备"命令到小米云服务，触发设备进行定位
2. **坐标系转换**：支持多种坐标系格式，可在配置时选择
   - 原始坐标（original）：设备返回的原始坐标
   - 国测局坐标（GCJ02）：适用于大部分中国地图服务
   - WGS84坐标：全球GPS标准坐标系，适用于国际地图服务

### 位置数据属性

位置追踪实体提供以下属性：

- **经纬度**：设备的地理位置坐标
- **精度**：位置数据的精确度（以米为单位）
- **最后更新时间**：设备位置信息的最后更新时间
- **坐标类型**：当前使用的坐标系类型
- **电量**：设备的电池电量百分比（如果设备支持）
- **设备型号**：小米设备的型号名称
- **IMEI**：设备的唯一标识符

### 手动触发定位

除了自动周期定位外，还可以通过服务调用手动触发设备定位：


### 坐标系选择

在集成配置过程中，您可以选择希望使用的坐标系类型：

- **original**：设备原始上报的坐标系
- **WGS84**：全球GPS标准坐标系，适用于国际地图服务
- **GCJ02**：国测局坐标系，适用于中国大陆地图服务

选择正确的坐标系对于准确显示设备在地图上的位置至关重要。

## 安装方法

### 使用HACS安装（推荐）

1. 确保您的Home Assistant已安装[HACS](https://hacs.xyz/)
2. 在HACS中添加此仓库作为自定义仓库：
   - 进入HACS > 集成
   - 点击右上角的三个点，选择"自定义仓库"
   - 添加URL `https://github.com/MagicStarTrace/xiaomi_cloud`，类别选择"Integration"
3. 在HACS中搜索"Xiaomi Cloud"并安装
4. 重启Home Assistant

### 手动安装

1. 下载最新版本
2. 解压并将`custom_components/xiaomi_cloud`目录复制到您Home Assistant的`custom_components`目录中
3. 重启Home Assistant

## 配置方法

1. 进入配置 > 集成
2. 点击"+"按钮添加新集成
3. 搜索"Xiaomi Cloud"并选择
4. 按照配置流程，输入您的小米账号凭据
5. 选择您希望使用的坐标系类型


如有问题和功能请求，请使用[GitHub问题跟踪器](https://github.com/MagicStarTrace/xiaomi-cloud/issues)。

---

![截图](https://raw.githubusercontent.com/MagicStarTrace/xiaomi_cloud/refs/heads/master/Initialisation-log.jpg)
![截图](https://raw.githubusercontent.com/MagicStarTrace/xiaomi_cloud/refs/heads/master/Add-Integration.jpg)
![截图](https://raw.githubusercontent.com/MagicStarTrace/xiaomi_cloud/refs/heads/master/User-Added.jpg)
![截图](https://raw.githubusercontent.com/MagicStarTrace/xiaomi_cloud/refs/heads/master/Muran-map.jpg)
![截图](https://raw.githubusercontent.com/MagicStarTrace/xiaomi_cloud/refs/heads/master/WGS84toGCJ-02-resolved-address-entities.jpg)
![截图](https://raw.githubusercontent.com/MagicStarTrace/xiaomi_cloud/refs/heads/master/Unable-Get-Address.jpg)
