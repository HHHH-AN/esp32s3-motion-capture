# ESP32-S3 Motion Capture

基于 ESP32-S3 的动作捕捉系统，包含传感器节点固件、电脑端数据接收、姿态解算与 3D 可视化。

## 硬件基线

- 主控：ESP32-S3-WROOM-1-N16R8
- 六轴 IMU：ICM-42688-P（SPI）
- 三轴磁力计：LIS2MDLTR（I2C）
- 电源管理：AXP2101（I2C + IRQ）
- 数据接口：USB Type-C / USB 2.0 Device

> 不要使用项目早期的 ICM-20948 驱动或寄存器定义。PCB 投板前必须复核原生 USB D-/D+ 引脚，软件不能把 ESP32-S3 原生 USB 任意映射到其他 GPIO。

## 目录与三人分工

| 目录 | 负责人分支 | 工作边界 |
| --- | --- | --- |
| `firmware_esp32s3/` | `feature/firmware-node` | 传感器/PMIC 驱动、统一采样、数据发送 |
| `pc_receiver/` | `feature/pc-receiver` | 串口接收、协议解析、校验与录制 |
| `analysis/`、`desktop_app/` | `feature/fusion-3d` | 标定、姿态融合、3D 模型与界面 |
| `docs/`、`samples/`、根目录 | `main` | 公共接口；修改前先建小 PR 协商 |

三条功能分支都从同一个初始提交创建。每位成员只在自己的目录中工作，公共协议变更应单独提交并先合入 `main`。

## 推荐联调顺序

1. 固件输出符合 `docs/data-protocol.md` 的样例帧。
2. 接收端完成解析、丢包检测和标准化落盘。
3. 姿态解算与 3D 端读取接收端的标准输出。
4. 三条分支分别通过 Pull Request 合入 `main`，建议使用 Squash merge。

## 开发基线

- 固件首选 ESP-IDF；共享配置放在 `sdkconfig.defaults`，本机生成的 `sdkconfig` 不提交。
- PC 端优先使用 Python 做离线验证，再决定 GUI/3D 技术栈。
- 大体积录制数据不要直接提交；小型、脱敏、可复现的测试样例放在 `samples/`。
- 密钥、Wi-Fi 密码、令牌和个人串口配置不得提交。

详细协作方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，硬件接口见 [docs/hardware-interface.md](docs/hardware-interface.md)。

## 许可证

当前尚未选择开源许可证。仓库公开不等于已授予复制、修改或再发布权；确定发布策略后再添加 `LICENSE`。
