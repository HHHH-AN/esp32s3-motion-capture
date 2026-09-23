> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# Motion Capture Wire Protocol v1

## 帧

所有多字节整数均为小端。未编码帧为：

| 偏移 | 字段 | 类型 | 值/说明 |
|---:|---|---|---|
| 0 | magic | 2 bytes | ASCII `MC`，即 `4D 43` |
| 2 | version | `u8` | `1` |
| 3 | message_type | `u8` | 见消息表 |
| 4 | payload_length | `u16` | 仅 payload 长度 |
| 6 | node_id | `u8` | 网关为 0，佩戴节点为 1..14 |
| 7 | sequence | `u32` | 每个发送节点独立递增，允许回绕 |
| 11 | device_timestamp_us | `u64` | 节点启动后的单调微秒时钟 |
| 19 | payload | bytes | 由消息类型决定 |
| 19+N | crc | `u16` | CRC16-CCITT-FALSE，小端 |

CRC 参数：poly `0x1021`、init `0xFFFF`、refin/refout `false`、xorout `0x0000`，覆盖 header 和 payload。

完整帧进行 COBS 编码，再追加 `00` 分隔符。解码器必须能忽略坏帧并从下一个 `00` 继续同步。

## 消息类型

| 名称 | 值 |
|---|---:|
| RAW_SAMPLE | 1 |
| RAW_BATCH | 2 |
| DEVICE_STATUS | 3 |
| CONTROL | 4 |
| CONTROL_ACK | 5 |
| TIME_SYNC | 6 |
| ERROR | 7 |

## RAW_SAMPLE

固定 24 字节：

| 字段 | 类型 | 比例 |
|---|---|---|
| accel_mg | `i16[3]` | 1 mg/LSB |
| gyro_dps_x10 | `i16[3]` | 0.1 deg/s/LSB |
| mag_uT_x10 | `i16[3]` | 0.1 uT/LSB |
| temperature_c_x100 | `i16` | 0.01 degC/LSB |
| mag_age_us | `u16` | 磁场样本相对当前 IMU 样本的年龄 |
| status_flags | `u16` | 有效性和故障位 |

标志位：

- bit 0: accel valid
- bit 1: gyro valid
- bit 2: mag valid
- bit 3: temperature valid
- bit 4: mag stale
- bit 5: FIFO overflow since previous sample
- bit 6: sample queue drop since previous sample
- bit 7: sensor bus error since previous sample
- 其余位保留并发送为 0

## RAW_BATCH

Payload 首字节为 `record_count`，其后重复：

```text
node_id u8
sequence u32
device_timestamp_us u64
raw_sample_payload 24 bytes
```

单条记录 37 字节。网关只聚合，不修改原节点的 sequence 和 timestamp。

## DEVICE_STATUS

以 1 Hz 发送，包含电池毫伏、电量百分比、充电/供电标志、实际采样率、FIFO 溢出、队列丢弃、总线错误、固件版本、配置版本和标定版本。

## 控制和兼容规则

- CONTROL 使用 TLV：`tag u8 + length u8 + value`。
- 改变采样率、节点角色、标定或流状态必须返回 CONTROL_ACK。
- 未识别消息类型可以跳过；不支持的协议版本必须拒绝。
- 接收端先兼容新版本，发送端后切换；旧版本读取能力至少保留一个里程碑。
