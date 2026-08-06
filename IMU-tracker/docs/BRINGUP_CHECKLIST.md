# Board bring-up checklist

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
