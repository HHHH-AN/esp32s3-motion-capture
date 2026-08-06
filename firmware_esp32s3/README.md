# ESP32-S3 固件

负责人分支：`feature/firmware-node`。

范围：ESP-IDF 工程、`board_pins.h`、AXP2101/ICM-42688-P/LIS2MDLTR 驱动、统一采样结构和 USB CDC/UART 数据发送。

首轮 bring-up 顺序：最小日志与烧录 → AXP2101 → ICM-42688-P WHO_AM_I → LIS2MDLTR WHO_AM_I → 统一采样 → 数据发送。
