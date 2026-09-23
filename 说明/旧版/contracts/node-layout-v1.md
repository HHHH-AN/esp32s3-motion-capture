> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# Node Layout v1

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
