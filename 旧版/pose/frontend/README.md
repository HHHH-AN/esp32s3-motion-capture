# 旧版/pose/frontend 使用说明

<a id="part-1"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Pose Web Frontend

React、TypeScript 与 Three.js 编写的动作捕捉可视化端。浏览器不直接连接 BLE，也不运行姿态融合；它只消费 Python Bridge 发出的版本化 WebSocket JSON。

## 启动

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

默认开发地址为 `http://127.0.0.1:5173`，Vite 将 `/api` 和 `/ws` 代理到 `http://127.0.0.1:8000`。可用环境变量覆盖：

```text
VITE_MOCAP_POSE_WS_URL=ws://127.0.0.1:8000/ws/pose
VITE_MOCAP_SKELETON_WS_URL=ws://127.0.0.1:8000/ws/skeleton
VITE_MOCAP_API_URL=http://127.0.0.1:8000
```

## 数据契约

- 单节点姿态：`type: "pose.frame.v1"`、`schema_version: 1`。
- 骨架：`type: "skeleton.frame.v1"`、`schema_version: 1`。
- 四元数顺序始终为 `[w,x,y,z]`。
- 项目坐标 `+X` 向前、`+Y` 向左、`+Z` 向上；渲染坐标映射为 `(-Y,Z,-X)`。
- 胸部无实体节点，必须由后端标记为 `virtual: true`。

收到的消息会先通过 `src/types/messages.ts` 做运行时校验，非法、未知版本或非有限数值不会进入状态和渲染流水线。

## 验证

```powershell
pnpm test
pnpm build
```

测试覆盖公共消息契约、坐标/四元数基变换和骨架帧插值。
