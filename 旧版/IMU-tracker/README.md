# 旧版/IMU-tracker 使用说明

<a id="part-1"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## IMU-tracker firmware

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


---

<a id="part-2"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Board bring-up checklist

Record the PCB revision, board UID, operator and date for every result. A blank
checkbox is not evidence of a pass.

- [ ] Visual inspection: shorts, reversed ICs, solder bridges and antenna keepout.
- [ ] USB schematic and PCB route D- to GPIO19 and D+ to GPIO20.
- [ ] EN and BOOT straps match the ESP32-S3-MINI-1U datasheet.
- [ ] 3.3 V and every enabled PMIC rail are measured before firmware writes PMIC registers.
- [ ] ROM download mode and recovery after a bad application are proven.
- [ ] Boot log reports 4 MB flash and 2 MB PSRAM.
- [ ] AXP2101 identity/status read succeeds; no rail write is performed.
- [ ] ICM-42688-P WHO_AM_I succeeds over SPI with CS idle high.
- [ ] LIS2MDLTR WHO_AM_I succeeds on the magnetometer-only I2C bus.
- [ ] Stationary acceleration magnitude is 0.95-1.05 g.
- [ ] Stationary gyro noise and bias are recorded.
- [ ] Magnetometer axes vary continuously during a slow rotation.
- [ ] Actual sensor-to-PCB matrices are recorded and reviewed.
- [ ] 100 Hz timestamps are monotonic for 30 minutes.
- [ ] USB raw stream passes CRC/sequence checks for 30 minutes.

Do not enable ESP-NOW, BLE, PMIC writes, sleep or OTA until the relevant earlier
checks have passed.


---

<a id="part-3"></a>

> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

## Troubleshooting

## No USB device

Check D-/D+ routing first. ESP32-S3 native USB is fixed to GPIO19/GPIO20. Enter
ROM download mode with BOOT and EN. Try a known data cable and inspect Windows
Device Manager before changing firmware.

## ICM-42688-P not detected

Confirm CS is high before SPI starts, inspect 3.3 V and ground, then check SCK,
MOSI and MISO on GPIO11/10/12. Reduce SPI to 1 MHz for diagnosis. Do not enable
FIFO or interrupts until polling works.

## LIS2MDLTR not detected

It is on its own bus: SDA GPIO35 and SCL GPIO36. Check pull-ups and scan only that
bus. The PMIC uses GPIO33/GPIO47 and must not share the same `TwoWire` object.

## AXP2101 status unavailable

Check the PMIC bus on SDA GPIO33 and SCL GPIO47. The IRQ on GPIO48 is active low.
The firmware intentionally does not change regulator or charge settings.

## CRC or sequence errors

Capture raw bytes before the decoder, confirm every COBS frame ends in `00`, and
compare against `旧版/contracts/golden`. CRC16-CCITT-FALSE covers header plus payload;
the two CRC bytes are appended little-endian before COBS encoding.

## Wireless overload

First switch the gateway to USB to separate radio ingress from BLE egress. Check
queue high-water marks, ESP-NOW receive drops, BLE notification failures and host
decoder gaps independently.
