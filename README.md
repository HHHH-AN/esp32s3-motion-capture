# ESP32-S3 Motion Capture

基于 14 个 ESP32-S3-MINI-1U-N4R2 佩戴节点和 1 个独立网关的动作捕捉系统。

## 数据链路

```text
ICM-42688-P + LIS2MDLTR
  -> 佩戴节点 100 Hz 原始九轴数据
  -> ESP-NOW
  -> 独立网关
  -> BLE / USB
  -> Python 解码、标定、融合、同步与骨架运动学
  -> WebSocket
  -> React + Three.js
```

## 目录

- `contracts/`：硬件、线协议、坐标、节点、JSON Schema 与 Golden Vectors。
- `IMU-tracker/`：PlatformIO + Arduino 固件。
- `pose/backend/`：Python 数据链路、算法和 FastAPI 服务。
- `pose/frontend/`：React + TypeScript + Three.js 可视化。

当前哪些部分只是“已编译”、哪些已经通过 Mock、哪些必须等待实板，统一记录在
[`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)。

## 三人开发环境

- 三人都安装 Git、GitHub Desktop 和 VS Code；先用 GitHub Desktop 完成登录、克隆、切换分支、提交和发起 PR。
- ZBC 额外安装 VS Code 的 PlatformIO IDE 扩展，以及板卡在 Windows 设备管理器中确实缺失时所需的 Espressif USB/JTAG 驱动。
- HAN 安装 Python 3.11 或 3.12 与 `uv`。
- 项目负责人安装 Node.js 22、pnpm 9；Python 后端联调时也安装 `uv`。

协作规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，各子项目的具体命令见其 README。

## 快速验证

```powershell
python contracts/validate_contracts.py

cd pose\backend
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest

cd ..\frontend
pnpm install
pnpm test
pnpm build

cd ..\..\IMU-tracker
pio run
```

没有硬件时，可启动 Python Mock 数据源并打开前端，验证 WebSocket、姿态立方体和骨架渲染。

## 分支

- `main`：经过 PR 和 CI 验证的公共基线。
- `ZBC`：固件和无线链路长期协作分支。
- `HAN`：Python 后端与算法长期协作分支。
- 项目负责人使用 `lead/mX-*` 短分支维护契约、前端和集成。

硬件实测门禁及当前限制见 `contracts/hardware-v1.md`。
