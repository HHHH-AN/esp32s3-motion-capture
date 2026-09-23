> **运行位置**：本文命令在代码仓库的 `源代码/BLE/` 中执行，说明文件所在文件夹不是程序目录。

# BLE 版：硬件连接与烧录

先按[无线连接步骤](BLE_README.md)配置和运行。本页主要介绍三种版本共用的传感器接线与烧录方法。

本工程基于 **ESP32-S3-MINI-1** 模块，通过 **SPI** 读取 **ICM-42688-P** 六轴惯性传感器（加速度计 + 陀螺仪），通过 **I²C** 读取 **LIS2MDLTR** 三轴磁力计，并将数据通过 USB 串口输出到电脑显示。

---

## 1. 硬件组成

| 器件 | 型号 | 封装 | 接口 |
|------|------|------|------|
| 主控 | ESP32-S3-MINI-1 (N4R2) | SMD 模块 | — |
| IMU | ICM-42688-P | LGA-14 (3.0×2.5 mm) | SPI |
| 磁力计 | LIS2MDLTR | LGA-12 (2.0×2.0 mm) | I²C |

> 注：实测该模块 Flash 为 **4 MB**（N4R2 变体），故 `platformio.ini` 中已配置 `board_build.flash_size = 4MB`。

---

## 2. 引脚连接

连接关系依据原理图网表文件 `Netlist_Schematic1_2026-08-26.tel` 与 ESP32-S3-MINI-1 数据手册（v1.7）核对推导得出。

### 2.1 ICM-42688-P（SPI）

| 功能 | ESP32-S3 GPIO | 模块引脚号 | ICM-42688 引脚 |
|------|--------------|-----------|----------------|
| IMU_SCK | GPIO12 | 16 | U10.13 SCLK |
| IMU_MOSI | GPIO11 | 15 | U10.14 SDI |
| IMU_MISO | GPIO13 | 17 | U10.1 SDO |
| IMU_/SS | GPIO10 | 14 | U10.12 CS |
| IMU_INT (可选) | GPIO9 | 13 | U10.4 INT1 |

### 2.2 LIS2MDLTR（I²C，器件地址 0x1E）

| 功能 | ESP32-S3 GPIO | 模块引脚号 | LIS2MDL 引脚 |
|------|--------------|-----------|--------------|
| I²C SCL | GPIO33 | 28 | U2.1 SCL/SPC |
| I²C SDA | GPIO34 | 29 | U2.4 SDA/SDI/SDO |
| INT/DRDY (可选) | GPIO47 | 27 | U2.7 INT/DRDY |

> 注意：LIS2MDL 使用 I²C 通信时，其 **CS 引脚（U2.3）必须接高电平**（VDD_IO）。“CS 悬空”是旧资料的描述；2026-09-14 导出的原理图已将 CS 接到 VDD_3V3。实际板卡是否连通仍需测量。

---

## 3. 输出数据格式

串口波特率 **115200**，每行一组数据（CSV 格式），约 20 Hz：

```
AccX(g),AccY(g),AccZ(g),GyrX(dps),GyrY(dps),GyrZ(dps),ICM温度(C),MagX(mG),MagY(mG),MagZ(mG),LIS温度(raw)
-0.0247,-0.5354,0.8613,0.669,0.637,0.349,29.14,-108.0,648.0,-16.5,-72
```

| 字段 | 含义 | 单位 |
|------|------|------|
| AccX/Y/Z | 三轴加速度 | g（重力加速度） |
| GyrX/Y/Z | 三轴角速度 | °/s（度每秒） |
| ICM温度 | ICM-42688 内部温度 | °C |
| MagX/Y/Z | 三轴磁场强度 | mG（毫高斯） |
| LIS温度 | LIS2MDL 温度传感器原始值 | LSB |

> 量程：加速度 ±8 g，陀螺仪 ±2000 °/s，磁场 ±49 gauss（1.5 mgauss/LSB）。

---

## 4. 环境要求

- [PlatformIO Core](https://platformio.org/install)（或 VS Code + PlatformIO 扩展）
- ESP32-S3 开发板/模块，USB 连接电脑

---

## 5. 编译与烧录

在工程根目录（`platformio.ini` 所在目录）执行：

```bash
# 编译
pio run

# 烧录（COM7 为示例端口，请按实际修改）
pio run -t upload --upload-port COM7
```

> 提示：
> - 本工程使用 ESP32-S3 **内置 USB-Serial/JTAG** 烧录/调试，无需外部 USB-TTL 转换器。
> - 若遇到 `Could not open COM7, the port is busy`（设备重启循环导致端口短暂不可用），可**多次重试**，或按住 **BOOT 键**再复位后烧录。
> - 查看可用串口：`pio device list`

---

## 6. 电脑上查看数据

1. 用 USB 线连接板子到电脑，确认设备管理器中枚举出串口（VID `303A`，PID `1001`，例如 `COM7`）。
2. 打开任意串口监视器，波特率选择 **115200**：
   - PlatformIO 命令：`pio device monitor -p COM7 -b 115200`
   - 或使用 VS Code 的 *Serial Monitor* 插件
   - 或 Arduino IDE 的串口监视器
3. 观察数据流即可。

---

## 7. 工程文件结构

```
源代码/
├── platformio.ini          # PlatformIO 工程配置
├── Netlist_Schematic1_2026-08-26.tel   # 原理图网表（硬件连接依据）
├── src/
│   └── main.cpp            # 主程序（传感器驱动 + 串口输出）
├── include/                # 头文件目录
├── lib/                    # 本地库目录
├── test/                   # 单元测试目录
└── .pio/                   # 构建产物（自动生成）
```

---

## 8. 常见问题排查

| 现象 | 可能原因 | 解决办法 |
|------|----------|----------|
| 串口无任何输出 | `Serial` 未走 USB 串口 | 确认 `platformio.ini` 中有 `-DARDUINO_USB_CDC_ON_BOOT=1` |
| 启动崩溃循环（`Detected size ... smaller than the size in the binary image header(8192k)`） | 上传时的 Flash 容量参数与实际不符 | 在 `platformio.ini` 中同时设置 `board_build.flash_size = 4MB` **和** `board_upload.flash_size = 4MB`，再重新编译上传 |
| 打开 COM 口提示"拒绝访问/端口被占用" | 有多个串口监视器进程同时打开了端口 | Windows 上一个 COM 口只能被一个程序占用：关闭多余的 `pio device monitor` / 串口工具，只保留一个监视器；也可在任务管理器结束多余的 `pio.exe` / `platformio.exe` 进程 |
| `[ICM-42688] 初始化失败` | SPI 接线错误 / 引脚映射不对 | 核对第 2 节引脚表 |
| `[LIS2MDL] 初始化失败` | I²C 接线错误 / CS 未拉高 | 核对引脚表；确认 LIS2MDL 的 CS 引脚接高电平 |
| 上传时报端口繁忙 | 设备正在重启，端口被占用 | 重试多次；或按住 BOOT 再复位后烧录 |
| 磁力计数据明显偏大 | 附近有强磁场干扰 | 远离电机、扬声器等磁性物体 |

---

## 9. 扩展说明

- 若更换为 **8 MB Flash** 的 `-N8` 模块：删除 `platformio.ini` 中的 `board_build.flash_size = 4MB`、`board_upload.flash_size = 4MB` 和 `board_build.partitions = default.csv` 三行（恢复为板级默认 8 MB 配置）。
- ICM-42688 初始化时会自动执行**陀螺仪零偏校准**（约 1~2 秒，期间请保持板子静止）。
- LIS2MDL 配置为连续测量模式 100 Hz，启用了偏移消除与数据块更新（BDU）。
