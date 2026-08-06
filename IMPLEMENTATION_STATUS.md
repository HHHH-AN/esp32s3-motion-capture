# Implementation Status

更新日期：2026-08-06。

本仓库已经形成可构建、可测试的三端软件基线，但不能把“代码存在或编译成功”当作实板里程碑通过。下表区分软件完成度和硬件验收状态。

| 阶段 | 当前软件状态 | 仍需关闭的门禁 |
|---|---|---|
| M0 | 硬件、坐标、节点、线协议、BLE、JSON Schema、Golden Vectors、CI 和 PR 规则已建立 | 原理图/PCB USB 必须改为 GPIO19/20；确认 BOOT/EN、供电轨和两颗传感器的 PCB 轴矩阵；补齐非 RAW 消息 payload 契约 |
| M1 | PlatformIO、FastAPI Mock、React/Three.js 闭环可运行 | 在全新开发机按 README 复现一次 |
| M2 | GPIO、SPI、两套独立 I2C、单调时钟、ISR 路由和 AXP 只读状态代码可编译 | 实测电源轨；验证 AXP IRQ；未确认前禁止写电压 |
| M3 | ICM/LIS 轮询与统一定点样本已实现；FIFO/INT 有独立实验环境 | 依次完成 WHO_AM_I、静止噪声、三轴方向、FIFO 字节和 30 分钟 100 Hz 实测 |
| M4 | C++/Python RAW_SAMPLE、RAW_BATCH、COBS、CRC、USB、记录和回放代码已实现 | USB 硬件修订后做 30 分钟无丢包验收；冻结 DEVICE_STATUS/CONTROL/ACK/ERROR payload |
| M5 | 标定求解、Mahony、磁干扰降级、NVS 容器和真实姿态立方体路径已实现 | 用真实录制验证 5 分钟漂移和三轴 90° 误差；实际标定值尚未装载到默认运行配置 |
| M6 | BLE UUID、6 字节分片、重组、扫描、连接和重连代码可编译/测试 | 实板 MTU/DLE/2M PHY、100 Hz、30 分钟和低于 1% 丢包验收 |
| M7 | ESP-NOW 叶节点/网关、10 ms RAW_BATCH、节点表、PC 重排和仿射时钟模型已实现 | TIME_SYNC payload 与无线请求/响应尚未冻结和接入；14 节点吞吐、p95 对齐及延迟未实测 |
| M8 | 公共人体 Profile、虚拟胸廓、运动学、SLERP 和 Three.js 骨架已在 Mock 闭环运行 | 真实设备 UID 映射、在线 T-pose 安装标定和 14 节点动作验收；在线安装标定 HTTP 当前明确返回 501 |
| M9 | 双 OTA 分区、流式更新、故障/看门狗/电源策略和版本化存储框架已建立 | OTA 下载、签名/版本策略、回滚确认、任务心跳接入和 2 小时实机耐久测试 |

## 已执行的软件验证

- `python contracts/validate_contracts.py`：通过。
- Python：`ruff check .` 通过，`pytest` 23 项通过。
- 前端：Vitest 17 项通过，TypeScript + Vite 生产构建通过。
- 固件：`node_usb`、`node_fifo_lab`、`node_ble`、`node_espnow`、`gateway_usb`、`gateway_ble` 六个环境均完成编译和链接。
- 浏览器：Mock 后端驱动 WebSocket、Three.js、节点状态和录制开始/停止闭环；页面运行错误为 0。
- Windows 本机没有系统 GCC，因此 `native` Unity 测试未在本机执行；GitHub Actions 已配置为在 Ubuntu 上执行它们，待 Contract PR 推送后产生远端结果。

## 明确保留的实现差异

- LIS2MDL 当前使用项目自有的最小寄存器封装，尚未冻结并 vendoring ST `lis2mdl_reg.c/.h` 快照。
- AXP2101 当前使用只读最小寄存器封装，尚未迁移到参考工程使用的 `XPowersLib@0.3.3`；这样可保证未实测电源轨前不发生配置写入。
- `TIME_SYNC`、`DEVICE_STATUS`、`CONTROL_ACK` 和 `ERROR` 的完整 payload 必须先经独立 Contract PR 冻结，接收端先兼容后再切换发送端。
- 传感器到 PCB 的变换矩阵故意保持 identity 并带硬件 TODO，不能视为真实方向标定。

下一步应从 M0 硬件门禁开始，而不是直接打开 FIFO、无线时间同步或 OTA。
