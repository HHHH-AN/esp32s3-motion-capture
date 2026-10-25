# ESP32-S3 惯性动作采集系统

使用 ESP32-S3、ICM-42688-P 和 LIS2MDL 采集惯性数据，通过 **USB 串口或 Wi-Fi TCP** 传到电脑，显示实时姿态并记录数据。

当前保留一套固件和一套共享上位机代码。单板开发台用于传感器、串口、姿态和录制调试；多节点监控用于比较多块板子的旋转。两者共享协议、坐标和姿态处理模块。

## 目前做到哪一步

| 项目阶段 | 当前状态 |
| --- | --- |
| 电路与硬件 | 已有初版硬件；本仓库保存程序与必要参考，硬件原始工程在仓库外的项目资料目录 |
| 单块板 USB | 已有串口枚举、实时姿态、校准、记录和回放功能；伙伴包包含相关历史验证 |
| 单块板 Wi-Fi | 同一固件支持热点 AP 或路由器 STA；已有单板 TCP 实测记录 |
| 多块板 Wi-Fi | A/B 两节点并发旋转显示已有实测记录，仍需复查动态效果和长期稳定性 |
| 三节点实验 | 已有预设、离线演示和采集分析程序；第三节点尚未完成实板联合验证 |
| 数据与可视化优化 | 有静置零偏校准、停稳保持和磁场检查；动态精度、安装标定等仍需改进 |

状态依据来自 **2026-10-25 伙伴交接包**。随包的历史实板记录见 [验证资料](docs/validation/README.md)，不代表本次目录整理重新完成了实板测试。完整边界见 [项目状态](docs/status.md)。

当前主线为 **USB → Wi-Fi → 多板**。BLE、ESP-NOW 和旧版全身系统没有纳入当前工程；历史源码可以从 Git 历史找回。

## 工程结构

```text
.
├── firmware/                 ESP32-S3 固件，USB 与 Wi-Fi 共用采集逻辑
│   ├── platformio.ini        A 节点与 B 节点构建环境
│   ├── src/main.cpp          传感器采集、节点标识、串口和 TCP 输出
│   └── include/              可提交的 Wi-Fi 配置示例与本机私有配置
├── host/                     电脑端程序
│   ├── dashboard/            协议、传输、姿态处理、录制和单板 HTTP 服务
│   ├── web/                  单板开发台和多节点监控页面
│   ├── motion_presets/       三节点实验分析与报告
│   ├── presets/              实验预设和端点示例
│   ├── tests/                Python 与 JavaScript 测试
│   ├── run_dashboard.py      单板开发台，默认 8000
│   ├── run_wifi_monitor.py   多节点旋转监控，默认 8010
│   └── run_motion_presets.py 离线演示、回放和三节点采集入口
├── tools/                    PowerShell 启动器、诊断和交付打包工具
├── docs/                     使用方法、工程状态及历史验证依据
├── .github/                  CI、代码归属和 PR 模板
├── .codex/                   代码级 AI 工作记录，由 project-workspace 管理
└── README.md                 GitHub 首页与工程入口
```

整体项目（本仓库上一层）的 `.codex/` 保存项目主线、硬件与软件协作及总体交接；本仓库的 `.codex/` 保存代码设计、构建、测试、调试和 Git 操作记录。

## 先运行电脑端

需要 Python **3.10 或更新版本**；CI 使用 3.12。在 PowerShell 中进入本仓库根目录，创建上位机环境：

```powershell
py -3.12 -m venv host/.venv
host/.venv/Scripts/python.exe -m pip install -r host/requirements.txt
```

`py -3.12` 要求本机已安装 Python 3.12。若只有其他版本，先用 `py -0p` 确认，再选择不低于 3.10 的解释器。

**USB 或单板 Wi-Fi 开发台：**

```powershell
.\tools\start_dashboard.ps1
```

打开 [单板开发台](http://127.0.0.1:8000)，在页面选择串口或 Wi-Fi，并填写实际 COM 号或 IP。使用页面前关闭占用串口的监视器。

**A/B 两节点旋转监控：**

```powershell
.\tools\start_wifi_monitor.ps1
```

打开 [多节点旋转监控](http://127.0.0.1:8010)。启动器默认使用 A=`192.168.4.1:9000`、B=`192.168.4.201:9000`；这是现有 A 热点、B 加入 A 的拓扑，运行前核实板卡配置与电脑网络。若地址不同，直接指定端点：

```powershell
cd host
.\.venv\Scripts\python.exe -B run_wifi_monitor.py --node A=192.168.4.1:9000 --node B=192.168.4.201:9000
```

每块板当前只接受一个 TCP 接收程序。单板开发台、多节点监控和实时实验采集应分别使用。

## 固件编译与烧录

在 VS Code 中直接打开 `firmware/`，使用 PlatformIO。首次烧录前，将 `include/wifi_config.example.h` 复制为 `include/wifi_config.h`，在本地填写网络参数；私有文件已被 Git 忽略。

```powershell
cd firmware
if (-not (Test-Path include/wifi_config.h)) {
    Copy-Item include/wifi_config.example.h include/wifi_config.h
}
pio run -e esp32-s3-devkitm-1
pio run -e esp32-s3-client-b
```

已有私有配置时保留原文件。默认环境用于 A；`esp32-s3-client-b` 用于加入 A 热点的 B，静态地址尾号为 201。重新烧录 B 时，配置必须与 A 的真实热点一致。编译命令只构建固件；确认板卡和实际串口后再执行上传：

```powershell
pio run -e esp32-s3-devkitm-1 -t upload --upload-port COM9
```

`COM9` 是命令示例，按本机设备管理器或 `pio device list` 的结果替换。第三块板需要独立地址配置，避免复用 B 的静态 IP。

如果 Windows 工具链在中文路径报找不到依赖文件或 `firmware.map`，可将仓库映射到空闲英文盘符，再打开对应工程：

```powershell
subst M: "E:\AAA动作捕捉系统\2.代码"
```

之后在 VS Code 打开 `M:\firmware`。盘符映射指向同一份文件；使用前确认 `M:` 空闲，重启后可能需要重新建立。

## 离线演示与验证

三节点预设演示不需要板子：

```powershell
.\tools\start_preset.ps1 -Preset upper_limb
```

测试从 `host/` 运行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
node --check web/app.js
node --check web/pose_math.js
node tests/test_pose_math.js
```

实验报告的 JavaScript 测试需要先生成四份演示报告，完整命令见 [GitHub CI](.github/workflows/ci.yml)。

## 接下来按什么顺序做

1. 在当前电脑复现单板 USB：确认有效数据、三轴方向与实时姿态。
2. 复现单板 Wi-Fi：确认 AP/STA、TCP 接收和断线恢复。
3. 复查 A/B 两节点：观察转动后停稳、动态一致性和长期数据质量。
4. 接入第三节点，再优化安装标定、数据处理和可视化。

详细操作见 [使用说明](docs/usage.md)，三节点预设见 [实验说明](docs/experiments.md)。当前位移是会漂移的估算；三节点对齐是近似时间对齐，不能视为硬件同步或精确人体关节角。
