> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# Coordinate Contract v1

## 项目世界坐标

使用右手坐标系：

- `+X`：人体前方。
- `+Y`：人体左方。
- `+Z`：人体上方。

所有向量进入线协议前先从传感器原生坐标转换到 PCB/board 坐标。

## 四元数

- 顺序固定为 `[w, x, y, z]`。
- `NodePose.quaternion_wxyz` 表示 `q_world_from_board`。
- 输出前必须归一化；范数误差不得超过 `1e-3`。
- 安装标定生成 `q_segment_from_board`，肢段世界姿态为：

```text
q_world_from_segment = q_world_from_board * inverse(q_segment_from_board)
```

## Three.js 映射

项目坐标 `(X_forward, Y_left, Z_up)` 映射到 Three.js：

```text
three = (-Y_left, Z_up, -X_forward)
```

向量和四元数必须使用同一基变换；禁止只交换位置轴而不转换旋转。

## 第一版限制

- 骨盆根位置固定为 `[0, 0, 0]`。
- 不对加速度做长期二次积分。
- 胸部没有实体节点，其世界旋转继承骨盆并标记 `virtual=true`。
