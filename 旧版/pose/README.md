# 旧版/pose 使用说明

<a id="part-1"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## pose

电脑端姿态解算、同步、骨架运动学和 3D 可视化。

- `backend/`：Python、FastAPI、串口/BLE/回放输入、标定、Mahony 融合和骨架输出。
- `frontend/`：React、TypeScript、Three.js、连接状态、诊断、标定向导和回放界面。

浏览器不直接读取 BLE 或原始 IMU 数据；所有设备通信和算法均由本地 Python 服务完成。

具体运行命令见两个子项目各自的 README。
