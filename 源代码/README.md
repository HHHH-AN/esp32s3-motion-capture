# 当前代码：总览与版本对比

<a id="part-1"></a>

## 动作捕捉项目：从这里开始

当前使用 `源代码/` 里的代码，有 USB、蓝牙、Wi-Fi 三个独立版本。**目前接入一个真实节点（右腕），另外 13 个节点是模拟显示，还不是完整的全身动作捕捉。**

各版本的接线、烧录、连接和记录说明已合并到各自 README，可在编辑器或 GitHub 中直接阅读。

## 我应该打开哪个文件夹？

| 你的目的 | 进入目录 | 操作说明 |
|---|---|---|
| 用 USB 连接板子与电脑 | `源代码/imu/` | [USB 版说明](imu/README.md#part-1) |
| 通过蓝牙无线连接 | `源代码/BLE/` | [蓝牙连接步骤](BLE/README.md#part-2) |
| 板子与电脑通过路由器连接 | `源代码/WIFI/` | [Wi-Fi 连接步骤](WIFI/README.md#part-2) |
| 看新版相对旧版改了什么 | `源代码/` | [版本对比和验证记录](README.md#part-2) |
| 看数据、记录与导出方法 | 对应版本目录 | [USB 界面说明](imu/README.md#part-2)、[BLE 界面说明](BLE/README.md#part-3)、[Wi-Fi 界面说明](WIFI/README.md#part-3) |

## 第一次运行

先安装 Python 3.11 或更新版本，以及 PlatformIO（可使用 VS Code 扩展）。在上表选中的版本文件夹打开终端，再执行：

```powershell
python -m pip install -r requirements.txt
python run_dashboard.py
```

浏览器打开 <http://127.0.0.1:8000>。一次只启动一个版本，避免默认端口被占用。板子首次使用或切换通信版本时，还需要按对应说明编译和烧录固件。

USB 基础版的默认串口是 COM21；如果你的串口不同，修改该版本 `dashboard/service.py` 中的 `port` 默认值。烧录、串口监视器和上位机不要同时占用同一个串口。

## 如何理解画面和数据？

- 页面出现 14 个节点，不代表连接了 14 块实物板。
- 数据约每秒 20 帧；当前格式没有设备时间戳、帧序号和节点编号。
- 丢包率是按数据到达间隔估算的，轨迹也不是绝对空间定位结果。
- 编译和软件测试通过，不代表已完成实板、无线连接或全身动作验收。

## 其余资料放在哪里？

| 目录或文件 | 用途 |
|---|---|
| `旧版/IMU-tracker/`、`旧版/pose/`、`旧版/contracts/` | 旧版固件、电脑端和接口参考；不要混用到当前版本 |
| [更新记录](../说明/项目管理.md#part-2) | 查看版本变化 |
| [协作说明](../说明/项目管理.md#part-1) | 团队分工、提交与审核规则 |
| [旧版完成情况](../旧版/README.md#part-1) | 查看旧版实现与未验收事项 |
| [旧版发布检查表](../旧版/README.md#part-2) | 旧版验收参考 |
| `配置/.ai/` | 给 AI 使用的设计和执行计划 |
| 项目根目录 `.codex/` | Codex 中间文件和检查报告 |

## 整理后的目录（2026-09-23）

```text
2.代码/
├── 配置/      AI 工作资料与配置说明
├── 说明/      项目管理、协作规则与更新记录
├── 源代码/    当前 USB（imu）、BLE、WIFI 三套工程
└── 旧版/      IMU-tracker、pose、contracts
```

本文命令中的运行目录指「2.代码」下面的源代码目录。根目录另外保留 Git/GitHub 所需的工具入口。Codex 工作文件放在项目根目录 `.codex/`。


---

<a id="part-2"></a>

## 当前 IMU 开发基线

2026-09-14 从用户提供的 `imu/` 导入，现位于 `源代码/`，以用户提供的代码为准。三个版本独立运行。2026-09-21 整理了文档，未修改功能代码。

| 目录 | 固件输出 | 电脑端连接 |
|---|---|---|
| [`源代码/`](imu/README.md#part-1) | USB 串口 | USB 串口 |
| [`BLE/`](BLE/README.md#part-2) | USB + BLE GATT Notify | USB 或 BLE |
| [`WIFI/`](WIFI/README.md#part-2) | USB + Wi-Fi TCP，默认端口 9000 | USB 或 Wi-Fi |

## 相对旧版的变化

| 项目 | 旧版 `旧版/IMU-tracker/` + `旧版/pose/` | 当前导入版本 |
|---|---|---|
| IMU GPIO | INT/CS/MOSI/SCK/MISO = 8/9/10/11/12 | 9/10/11/12/13，与 9 月 14 日导出的原理图一致 |
| 磁力计 GPIO | SDA/SCL = 35/36 | SDA/SCL/DRDY = 34/33/47；DRDY 定义为可选 |
| 电源逻辑 | AXP2101 只读探测 | 无 AXP2101 驱动；新版原理图使用 BQ24074 + TPS63802 |
| 固件结构 | 模块化驱动、节点/网关环境 | 每个版本独立 `src/main.cpp`，ICM42688 库 + LIS2MDL 寄存器访问 |
| 数据链路 | 100 Hz，ESP-NOW 汇聚，COBS/CRC 二进制协议 | 约 20 Hz，11 列换行 CSV，单设备直连 |
| 姿态解算 | Mahony、多节点时钟模型和重排 | 互补融合，使用主机到达时间 |
| 可视化 | React / TypeScript / Three.js | FastAPI + 静态 HTML/CSS/JavaScript |
| 节点状态 | 14 节点架构及 Mock 骨架 | 右腕 1 个真实输入，其余 13 个静止模拟节点 |
| 记录 | 旧版原始流与派生数据 | 中文表头 CSV、记录预览、三个 CSV 的 ZIP 导出 |

当前 CSV 不包含节点 ID、设备时间戳或帧序号，不能接入旧版二进制解码器，也不能据此宣称完成 14 节点同步。页面丢包率是到达间隔估算值，轨迹是骨骼约束相对位置或短时趋势，非绝对定位。

## 运行

使用 Python 3.11 或更新版本及 PlatformIO。在选定的版本目录中执行：

```powershell
python -m pip install -r requirements.txt
python run_dashboard.py
```

打开 <http://127.0.0.1:8000>。三个版本共用默认服务端口，一次启动一个版本。
USB 基础版默认串口为 COM21；BLE、Wi-Fi 版使用各自页面的连接控件。

固件编译：

```powershell
pio run
```

Wi-Fi 版编译前，在 `WIFI/` 目录执行：

```powershell
Copy-Item include/wifi_config.example.h include/wifi_config.h
```

随后在本地配置路由器名称和密码。`wifi_config.h` 已忽略，不提交真实凭据。
运行时请进入本仓库 `源代码/WIFI/`；连接说明已更新为本机项目路径。

## 导入范围与资料差异

- 导入 78 个源文件、依赖配置、测试、说明、网表和界面截图，并逐文件核对 SHA-256。
- 未导入个人录制、Python 缓存、IDE 配置、`.wifi-staging` 和本地 Wi-Fi 凭据。
- 保留旧版目录供追溯；开发入口为本目录。
- 三份上游 README 的“磁力计 CS 悬空”说明来自旧原理图；9 月 14 日导出的原理图已将 CS 接到 VDD_3V3。实际 PCB 连通性仍需实测。
- 附带的网表日期为 2026-08-26；最新硬件 PDF 位于项目根目录 `1.硬件与数据手册/4.动捕项目硬件原理/`。

## 2026-09-14 导入时的验证记录

- Python 3.12 独立环境：USB 9 项、BLE 13 项、Wi-Fi 14 项单元测试，合计 36 项全部通过。
- 三个 `web/app.js` 均通过 `node --check`。
- 三套 FastAPI 均通过首页、静态 JavaScript、14 节点状态接口和 WebSocket 首帧检查。
- 新增 `.github/workflows/imu.yml`，分别验证三套上位机与固件，Wi-Fi 构建使用示例配置。
- [GitHub Actions 验证](https://github.com/Hao5200000/esp32s3-motion-capture/actions/runs/34841726595)：USB、BLE、Wi-Fi 三套固件全部编译成功，三套上位机测试亦全部通过（源代码提交 `f5e5ab2`）。
- 本机原有 PlatformIO 环境缺少 `idna` 且平台依赖安装失败；隔离环境下载较慢，固件结论采用上述干净 Ubuntu CI 的实际构建结果。
- 导入文件保留上游行尾空白和末尾空行，`git diff --check` 会报告这些已有格式问题；未为格式整理改写源文件。
- 本次未烧录、未连接硬件，未进行 USB/BLE/Wi-Fi 真实通信或全身动作验收。原始资料中的实测叙述不作为本次硬件验收证据。
