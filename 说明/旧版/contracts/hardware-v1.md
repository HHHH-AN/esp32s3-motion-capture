> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# Hardware Contract v1

## 权威来源

- 原理图：`1.硬件与数据手册/4.改后原理图和PCB/SCH_Schematic1_1-P1_2026-08-06.pdf`
- EDA 工程：同目录的 `.eprj2`
- 实际主控：`ESP32-S3-MINI-1U-N4R2`
- 存储：4 MB Flash、2 MB QSPI PSRAM
- 逻辑电源：3.3 V

## GPIO

| 外设 | 信号 | GPIO | 行为 |
|---|---|---:|---|
| ICM-42688-P | INT1 | 8 | 高电平有效、上升沿；ISR 只通知任务 |
| ICM-42688-P | CS | 9 | 低有效；启动最先拉高 |
| ICM-42688-P | MOSI | 10 | SPI 输出 |
| ICM-42688-P | SCK | 11 | SPI 时钟 |
| ICM-42688-P | MISO | 12 | SPI 输入 |
| LIS2MDLTR | SDA | 35 | MAG I2C |
| LIS2MDLTR | SCL | 36 | MAG I2C |
| AXP2101 | SDA | 33 | PMIC I2C |
| AXP2101 | SCL | 47 | 原理图网络名 `SCK` |
| AXP2101 | IRQ | 48 | 低电平有效、下降沿；ISR 只通知任务 |
| Native USB | D- | 19 | ESP32-S3 固定功能 |
| Native USB | D+ | 20 | ESP32-S3 固定功能 |

ICM `CLKIN` 和 LIS 中断均未连接。固件不得为它们声明虚构的 GPIO。

## 阻断项

当前导出的原理图仍把 USB 画在 GPIO18/19。进入 USB CDC 实机验收前必须完成：

1. 原理图改为 D-→GPIO19、D+→GPIO20。
2. PCB 网络同步修订，或对已生产首板完成割线/飞线。
3. 用万用表检查 Type-C 到 MINI 模组对应焊盘的连续性。
4. 导出带新日期或新 PCB revision 的 PDF。

在阻断项关闭前，USB 相关代码只能做编译和主机测试，不能宣告实机通过。

## 上板前必须记录

- ICM 封装 X/Y/Z 到 PCB 坐标的有符号置换矩阵。
- LIS 封装 X/Y/Z 到 PCB 坐标的有符号置换矩阵。
- AXP2101 上电后的 3.3 V 实测值和输出轨配置。
- BOOT/EN、首次烧录及崩溃恢复路径。

这些值未确认前，驱动允许只读识别芯片，但不得写 PMIC 电压，也不得将坐标标记为“已校准”。
