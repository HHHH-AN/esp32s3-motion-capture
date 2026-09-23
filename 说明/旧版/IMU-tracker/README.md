> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# IMU-tracker firmware

ESP32-S3-MINI-1U-N4R2 motion-capture wearable-node and independent-gateway
firmware, built with PlatformIO and the Arduino framework.

## Safety and verification status

- Pins follow the MINI software contract: ICM SPI/INT on GPIO8-12, LIS2MDLTR
  I2C on GPIO35/36, AXP2101 I2C/IRQ on GPIO33/47/48 and native USB on GPIO19/20.
- The AXP2101 wrapper is deliberately read-only until every regulator and
  charging value has been measured on the final PCB. XPowersLib 0.3.3 was
  evaluated but its AXP2101 `begin()` calls `disableTSPinMeasure()`, a register
  write, so the M2 read-only gate intentionally uses a local probe instead.
- Sensor polling is the default. `MOCAP_USE_ICM_INTERRUPT=1` compiles the
  GPIO8 ISR -> task notification -> FIFO batch path, but must not be deployed
  before its polarity, packet bytes and overflow recovery pass real-board tests.
- Sensor-to-PCB matrices are identity placeholders, clearly marked in
  `sensor_frame.cpp`; replace them only after physical axis verification.
- No hardware acceptance result is claimed by this repository.
- The official ST `lis2mdl_reg.c/.h` snapshot is not vendored yet. Select and
  record an exact upstream revision/license before replacing the small local
  read/poll wrapper; this is an explicit M3 follow-up, not a completed artifact.

## Install

Install Git, VS Code and the PlatformIO IDE extension. On Windows, install the
Espressif USB/JTAG driver only if Device Manager does not recognize the board.

## Build and test

```powershell
pio run -e node_usb
pio run -e node_fifo_lab
pio run -e node_ble
pio run -e node_espnow
pio run -e gateway_usb
pio run -e gateway_ble
pio test -e native
```

- `node_usb`: conservative polling and USB raw-stream build.
- `node_fifo_lab`: compile/bench path for GPIO8 ISR and FIFO; never enable it
  before the polling and logic-analyzer bring-up gates pass.
- `node_ble`: M6 single-board BLE validation build (`MOCAP-NODE-xx`).
- `node_espnow`: wearable node sending raw frames to the gateway.
- `gateway_usb`: ESP-NOW gateway forwarding 10 ms `RAW_BATCH` frames by USB.
- `gateway_ble`: the same gateway using `MOCAP-GW-00` and the contracted BLE GATT
  profile. BLE notifications use the contracted six-byte fragment header.

The native protocol test contains an exact byte copy of
`旧版/contracts/golden/raw-frame-v1.json` and fails if the firmware encoder drifts.

## First board bring-up

1. Verify 3.3 V and all enabled PMIC rails with a meter.
2. Confirm the schematic/PCB route D- to GPIO19 and D+ to GPIO20.
3. Prove BOOT + EN recovery and flash `node_usb`.
4. Confirm the log reports 4 MB flash and 2 MB PSRAM.
5. Confirm AXP2101, ICM-42688-P and LIS2MDLTR identities.
6. Keep the board still and inspect gravity magnitude and gyro bias.
7. Rotate one PCB axis at a time and record both sensor-to-PCB matrices.
8. Run the USB stream and host CRC/sequence checker for 30 minutes.
9. Only then test the gated FIFO, BLE and ESP-NOW builds.

See `docs/BRINGUP_CHECKLIST.md` and `docs/TROUBLESHOOTING.md` for detailed gates.
