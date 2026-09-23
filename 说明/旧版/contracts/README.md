> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# 公共契约

`旧版/contracts/` 是固件、Python 后端和 Web 前端共同遵守的唯一接口来源。

## 变更规则

1. 先修改契约、Schema 和 Golden Vectors，再修改消费者，最后修改生产者。
2. 固件和 Python 的二进制协议必须逐字节一致；姿态和运动学使用数值容差。
3. `旧版/contracts/golden/` 只能在独立的 Contract PR 中修改。
4. 不允许在实现 PR 中调整期望结果来迁就错误代码。
5. 不兼容变更必须增加协议或 Schema 主版本；兼容字段扩展增加次版本。

运行契约自检：

```powershell
python 旧版/contracts/validate_contracts.py
```

## 当前版本

- Wire protocol: `1`
- Pose schema: `pose.frame.v1`
- Skeleton schema: `skeleton.frame.v1`
- Body profile: `human-14-v1`
