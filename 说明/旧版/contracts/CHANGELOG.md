> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# 契约变更记录

## 1.0.0 - 2026-08-06

- 冻结 ESP32-S3-MINI-1U-N4R2 板级接口。
- 定义 COBS + CRC16-CCITT-FALSE 二进制协议 v1。
- 定义 `RAW_SAMPLE` 的 24 字节定点载荷。
- 定义 `pose.frame.v1` 和 `skeleton.frame.v1`。
- 定义 14 个佩戴节点和独立网关节点。
- 将胸部定义为随骨盆运动的虚拟骨段。
