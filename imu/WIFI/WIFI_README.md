# ESP32-S3 IMU Wi-Fi TCP 通信版

本项目让 ESP32-S3 和电脑连接同一个路由器。ESP32-S3 使用 DHCP 获取局域网地址，并在 TCP 端口 9000 发送约 20 Hz、11列、换行结尾的 CSV。USB串口输出同时保留。

## 1. 配置路由器

编辑 `include/wifi_config.h`：

```cpp
#define WIFI_SSID "路由器名称"
#define WIFI_PASSWORD "路由器密码"
#define WIFI_TCP_PORT 9000
```

ESP32-S3仅支持 2.4 GHz Wi-Fi，请确保该名称对应2.4 GHz网络。配置文件已加入 `.gitignore`，不要把真实密码提交到仓库。

## 2. 编译与烧录

```powershell
cd D:\han_study\summer_program\imu\WIFI
python -m platformio run
python -m platformio run -t upload --upload-port COM21
```

## 3. 获取 ESP32 地址

```powershell
python -m platformio device monitor -p COM21 -b 115200
```

找到以下输出并记下 IP：

```text
[WiFi] Connected
[WiFi] IP: 192.168.1.120
[TCP] Listening on port 9000
```

关闭串口监视器后启动上位机：

```powershell
python run_dashboard.py
```

打开 <http://127.0.0.1:8000>，选择 `Wi-Fi`，输入串口日志中的 IP 和端口 `9000`，然后连接。

## 4. 当前限制

当前 CSV 没有帧序号和设备时间戳，而且 TCP 会自动重传网络数据。因此页面显示的是应用层帧率、到达间隔估算丢包和连接稳定性，不能表示真实无线丢包率或精确端到端延迟。精确测试需要后续 UDP 协议加入序号和设备时间戳。
