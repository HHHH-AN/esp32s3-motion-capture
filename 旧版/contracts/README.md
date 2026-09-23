# 旧版/contracts 使用说明

<a id="part-1"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## BLE Profile v1

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


---

<a id="part-2"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## 契约变更记录

## 1.0.0 - 2026-08-06

- 冻结 ESP32-S3-MINI-1U-N4R2 板级接口。
- 定义 COBS + CRC16-CCITT-FALSE 二进制协议 v1。
- 定义 `RAW_SAMPLE` 的 24 字节定点载荷。
- 定义 `pose.frame.v1` 和 `skeleton.frame.v1`。
- 定义 14 个佩戴节点和独立网关节点。
- 将胸部定义为随骨盆运动的虚拟骨段。


---

<a id="part-3"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Coordinate Contract v1

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


---

<a id="part-4"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Hardware Contract v1

## 权威来源

- 原理图：`1.硬件与数据手册/4.改后原理图和PCB/SCH_Schematic1_1-P1_2026-08-06.pdf`
- EDA 工程：同目录的 `.eprj2`
- 实际主控：`ESP32-S3-MINI-1U-N4R2`
- 存储：4 MB Flash、2 MB QSPI PSRAM
- 逻辑电源：3.3 V

## GPIO

| 外设 | 信号 | GPIO | 行为 |
|---|---|---:|---|
| ICM-42688-P | INT1 | 8 | 高电平有效、上升沿；ISR 只通知任务 |
| ICM-42688-P | CS | 9 | 低有效；启动最先拉高 |
| ICM-42688-P | MOSI | 10 | SPI 输出 |
| ICM-42688-P | SCK | 11 | SPI 时钟 |
| ICM-42688-P | MISO | 12 | SPI 输入 |
| LIS2MDLTR | SDA | 35 | MAG I2C |
| LIS2MDLTR | SCL | 36 | MAG I2C |
| AXP2101 | SDA | 33 | PMIC I2C |
| AXP2101 | SCL | 47 | 原理图网络名 `SCK` |
| AXP2101 | IRQ | 48 | 低电平有效、下降沿；ISR 只通知任务 |
| Native USB | D- | 19 | ESP32-S3 固定功能 |
| Native USB | D+ | 20 | ESP32-S3 固定功能 |

ICM `CLKIN` 和 LIS 中断均未连接。固件不得为它们声明虚构的 GPIO。

## 阻断项

当前导出的原理图仍把 USB 画在 GPIO18/19。进入 USB CDC 实机验收前必须完成：

1. 原理图改为 D-→GPIO19、D+→GPIO20。
2. PCB 网络同步修订，或对已生产首板完成割线/飞线。
3. 用万用表检查 Type-C 到 MINI 模组对应焊盘的连续性。
4. 导出带新日期或新 PCB revision 的 PDF。

在阻断项关闭前，USB 相关代码只能做编译和主机测试，不能宣告实机通过。

## 上板前必须记录

- ICM 封装 X/Y/Z 到 PCB 坐标的有符号置换矩阵。
- LIS 封装 X/Y/Z 到 PCB 坐标的有符号置换矩阵。
- AXP2101 上电后的 3.3 V 实测值和输出轨配置。
- BOOT/EN、首次烧录及崩溃恢复路径。

这些值未确认前，驱动允许只读识别芯片，但不得写 PMIC 电压，也不得将坐标标记为“已校准”。


---

<a id="part-5"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Node Layout v1

| node_id | role | segment | 说明 |
|---:|---|---|---|
| 0 | gateway | none | 独立 ESP-NOW→BLE/USB 网关 |
| 1 | wearable | pelvis | 根姿态 |
| 2 | wearable | head | 头部 |
| 3 | wearable | left_upper_arm | 左上臂 |
| 4 | wearable | right_upper_arm | 右上臂 |
| 5 | wearable | left_forearm | 左前臂 |
| 6 | wearable | right_forearm | 右前臂 |
| 7 | wearable | left_hand | 左手 |
| 8 | wearable | right_hand | 右手 |
| 9 | wearable | left_thigh | 左大腿 |
| 10 | wearable | right_thigh | 右大腿 |
| 11 | wearable | left_shank | 左小腿 |
| 12 | wearable | right_shank | 右小腿 |
| 13 | wearable | left_foot | 左脚 |
| 14 | wearable | right_foot | 右脚 |

MAC 地址只用于发现和配对；业务逻辑只使用写入 NVS 的 `node_id`。重复 ID 必须拒绝进入实时骨架。

胸部、左右肩和左右髋关节由人体配置生成，不占用 node_id。胸部旋转继承骨盆，因此首版不能测量胸椎相对骨盆的独立扭转。


---

<a id="part-6"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## 公共契约

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


---

<a id="part-7"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Motion Capture Wire Protocol v1

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
