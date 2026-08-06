# 节点到电脑的数据协议

状态：`v0.1-draft`。该文件属于三方公共接口；字段、单位、坐标系或编码发生变化时，必须先单独评审。

## 逻辑采样结构

每个采样包含：

| 字段 | 类型 | 单位/说明 |
| --- | --- | --- |
| `protocol_version` | `uint8` | 当前为 `1` |
| `sequence` | `uint32` | 单调递增，用于检测丢帧，溢出后回绕 |
| `timestamp_us` | `uint64` | 节点启动后的单调微秒时间戳 |
| `accel_x/y/z` | `float32` | m/s² |
| `gyro_x/y/z` | `float32` | rad/s |
| `mag_x/y/z` | `float32` | µT |
| `battery_mv` | `uint16` | 电池电压，无法读取时为 `0` |
| `status` | `uint16` | 状态位掩码，定义见下文 |

## Bring-up 阶段 CSV 传输

USB CDC 或 UART 每个采样发送一行 UTF-8/ASCII 文本，逗号分隔、句点作为小数点、换行符 `\n`：

```text
MOCAP1,sequence,timestamp_us,ax,ay,az,gx,gy,gz,mx,my,mz,battery_mv,status
```

示例数据放在 `samples/imu_frames_v1.csv`。后续如切换二进制协议，逻辑字段和单位保持不变，并通过新的协议版本区分。

## 坐标系

- 传感器原始轴先按芯片数据手册输出。
- 板级坐标变换矩阵待 PCB 丝印方向确认后补充。
- PC 接收层只解析与记录，不擅自交换或取反坐标轴。
- 标定与融合层负责把板级坐标转换到项目统一坐标系。

## 状态位（初稿）

| 位 | 含义 |
| --- | --- |
| 0 | IMU 数据有效 |
| 1 | 磁力计数据有效 |
| 2 | PMIC/电池数据有效 |
| 3 | 采样溢出或丢样 |
| 4–15 | 保留，发送端必须置 0 |
