> **运行位置**：本文命令在代码仓库的 `源代码/BLE/` 中执行，说明文件所在文件夹不是程序目录。

# ESP32-S3 IMU BLE 通信实验版

本目录是独立的 BLE 通信版本，原 USB 串口工程保持不变。传感器仍以约 20 Hz 生成原来的 11 列 CSV；同一帧保留 USB 串口调试输出，并通过 BLE GATT Notify 发送。

## 安装与运行

```powershell
python -m pip install -r requirements.txt
pio run
pio run -t upload --upload-port COM21
python run_dashboard.py
```

浏览器打开 <http://127.0.0.1:8000>，通信方式选择 `BLE`，点击“扫描设备”，选择 `IMU-MOTION-01` 后连接。

## BLE 参数

- 设备名：`IMU-MOTION-01`
- Service UUID：`7d2a0001-6c8a-4f6b-9c65-4f4d55494d55`
- Notify UUID：`7d2a0002-6c8a-4f6b-9c65-4f4d55494d55`
- 数据格式：原 11 列 CSV，以换行符结束
- 接收端：Windows Python 后端，依赖 Bleak

网页可在 `USB串口` 与 `BLE` 之间切换，同一时间只连接一种通信方式。两种方式共用 CSV 解析、姿态融合、记录与质量统计，便于比较帧率、估算丢包率、无效帧和稳定性。

## 当前限制

第一版未加入帧序号和设备时间戳，因此丢包率仍为到达间隔估算值，不能表示严格的真实丢包率或端到端延迟。需要精确比较时，应在下一版协议加入设备侧帧序号和单调时钟时间戳。
