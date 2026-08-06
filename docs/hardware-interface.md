# 硬件—软件接口基线

本表来自 2026-08-06 硬件到软件交接记录。PCB 同学导出正式 netlist 或引脚表后，应再次逐项复核。

## ICM-42688-P（SPI）

| 功能 | 原理图网络名 | ESP32-S3 GPIO |
| --- | --- | --- |
| 中断 | `IMU_INTERUPT` | GPIO7 |
| 片选 | `IMU_/SS` | GPIO8 |
| MOSI | `IMU_MOSI` | GPIO9 |
| SCK | `IMU_SCK` | GPIO10 |
| MISO | `IMU_MISO` | GPIO11 |
| 外部时钟/同步 | `CLKIN` | GPIO17 |

原理图网络名中的 `INTERUPT` 是既有拼写；代码变量可命名为 `IMU_INT_PIN`，并在注释中保留原网络名。

## LIS2MDLTR（I2C）

| 功能 | 原理图网络名 | ESP32-S3 GPIO |
| --- | --- | --- |
| SDA | `MAG_SDA` | GPIO35 |
| SCL | `MAG_SCL` | GPIO36 |

ICM-42688-P 只有加速度计与陀螺仪。九轴姿态数据需要与 LIS2MDLTR 的三轴磁场数据融合。

## AXP2101（I2C + IRQ）

| 功能 | 原理图网络名 | ESP32-S3 GPIO |
| --- | --- | --- |
| SDA | `SDA` | GPIO33 |
| SCL | `SCK` | GPIO47 |
| IRQ | `IRQ` | GPIO48 |

这里的 `SCK` 是 PMIC 的 I2C 时钟网络，不是 `IMU_SCK`。

## 待硬件确认

- 原理图疑似把 `DP-`、`DP+` 接到 GPIO18、GPIO19；ESP32-S3 原生 USB 通常使用 GPIO19、GPIO20。投板前必须确认，软件无法任意重映射原生 USB。
- 确认 GPIO0 BOOT、EN RESET 按键、测试点或自动下载电路。
- 确认 AXP2101 上电默认电源轨能满足主控和两颗传感器的供电要求。
