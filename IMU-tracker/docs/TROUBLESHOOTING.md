# Troubleshooting

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
compare against `contracts/golden`. CRC16-CCITT-FALSE covers header plus payload;
the two CRC bytes are appended little-endian before COBS encoding.

## Wireless overload

First switch the gateway to USB to separate radio ingress from BLE egress. Check
queue high-water marks, ESP-NOW receive drops, BLE notification failures and host
decoder gaps independently.
