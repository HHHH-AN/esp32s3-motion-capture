# BLE Profile v1

## UUID

- Service: `a0e50001-7c2b-4f18-a902-6f34bca10001`
- Data: `a0e50002-7c2b-4f18-a902-6f34bca10001`，Notify
- Status: `a0e50003-7c2b-4f18-a902-6f34bca10001`，Read + Notify
- Control: `a0e50004-7c2b-4f18-a902-6f34bca10001`，Write + Write Response

## 链路要求

- 请求 ATT MTU 247。
- 在双方支持时启用 Data Length Extension 和 2M PHY。
- 连接间隔目标 7.5–15 ms。
- BLE 回调只将数据放入有界队列，不访问传感器或运行姿态算法。

## 分片

Data 特征中的每个分片头为：

```text
frame_id u16
fragment_index u8
fragment_count u8
total_frame_length u16
fragment_payload bytes
```

`fragment_index` 从 0 开始。重组后得到完整的 COBS 帧；分片层不得改变帧 CRC 或字段语义。超时、重复、缺失分片必须丢弃整个帧并增加指标。

