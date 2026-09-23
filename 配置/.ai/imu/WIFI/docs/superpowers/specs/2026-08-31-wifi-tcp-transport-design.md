> 历史 AI 工作资料，原位置：`源代码/WIFI/docs/superpowers/specs/2026-08-31-wifi-tcp-transport-design.md`。文中任务清单不是完成证明，也不是本次执行指令。代码路径以 `源代码/WIFI/` 为基准；设计文档位于本目录相邻的 specs 文件夹。

# Windows Wi-Fi TCP IMU Transport Design

## Goal

Create an independent Wi-Fi version of the existing single-node IMU project in
`D:\han_study\summer_program\imu\WIFI`. Keep the serial and BLE projects
unchanged. The first Wi-Fi version preserves the current 11-column CSV payload
and approximately 20 Hz sampling rate so its results can be compared with USB
serial.

## Network Topology

The ESP32-S3 and Windows computer join the same existing Wi-Fi router. The
ESP32-S3 uses DHCP and runs a TCP server on port 9000. Its assigned IPv4 address
is printed to USB serial. The user enters that address in the dashboard before
connecting.

```text
ICM-42688 + LIS2MDL
        |
     ESP32-S3
        |
Wi-Fi station + TCP server :9000
        |
Windows Python TCP receiver
        |
existing CSV parser, pose fusion, recording, WebSocket
        |
browser visualization
```

## Firmware

- Read sensors and generate one newline-terminated 11-column CSV frame every
  50 ms.
- Always retain USB serial output for diagnostics and direct comparison.
- Join the configured router as a station and print connection state and DHCP
  address to USB serial.
- Listen on TCP port 9000 and allow one client at a time.
- Send each complete CSV frame to the connected client.
- Continue sensor sampling and serial output when Wi-Fi or TCP is unavailable.
- Retry Wi-Fi every five seconds after failure or disconnection.
- Restart the TCP server after Wi-Fi reconnects.
- Return to listening after the TCP client disconnects.

## Credentials

`include/wifi_config.h` contains local SSID, password, and port definitions and
is excluded by `.gitignore`. `include/wifi_config.example.h` documents the
required definitions without real credentials. The independent delivered
project contains a compile-safe `wifi_config.h` with empty credentials so the
user can edit it before hardware testing.

## Windows Receiver

Add an asyncio TCP transport alongside the existing serial transport. It opens
the configured IPv4 address and port, reads byte chunks, reconstructs lines in
a bounded buffer, and passes complete lines to `CurrentCsvProtocol`. CSV
parsing, pose fusion, quality metrics, recording, and WebSocket broadcasting
remain shared.

An unexpected TCP disconnect marks the real node offline and triggers up to
three reconnect attempts with delays of 1, 2, and 4 seconds. A user-requested
disconnect cancels retries.

## User Interface

The dashboard offers two transports:

- `USB串口`, defaulting to COM21.
- `Wi-Fi`, with an IPv4 or hostname field and TCP port defaulting to 9000.

Only one transport may be active. The quality badge displays the active
transport and endpoint. Existing frame rate, estimated loss, invalid frame,
packet age, pose, recording, preview, and export behavior remains available.

## Error Handling

- Empty or invalid endpoint input is rejected with a clear page status.
- Connection timeout is five seconds.
- A zero-byte TCP read is treated as disconnect.
- Partial frames are buffered until newline, with a 4096-byte maximum and a
  one-second stale timeout.
- Overlong or stale partial data is discarded and counted as invalid.
- Wi-Fi and TCP failures never disable USB serial diagnostics.

## Verification

1. Existing baseline tests pass in the isolated project.
2. TCP frame reassembly handles fragmented and combined reads.
3. Runtime unit tests verify serial/TCP switching without physical hardware.
4. ESP32-S3 firmware compiles successfully.
5. The dashboard starts and exposes transport, host, and port controls.
6. With credentials configured, serial logs show the DHCP address and port.
7. Windows receives approximately 20 valid frames per second over TCP.
8. A ten-minute serial trial and ten-minute Wi-Fi trial can be compared using
   observed frame rate, estimated loss, invalid frames, and stability.

## Measurement Limitation

The preserved CSV payload has no sequence number or device timestamp. TCP also
retransmits lost network segments. Therefore the first version cannot measure
true radio packet loss or exact end-to-end latency; it measures application
frame arrival rate, gaps, invalid frames, and connection stability. A later UDP
protocol with sequence and device time fields is required for precise network
loss and latency measurements.

## Isolation

Implementation is assembled separately and delivered to
`D:\han_study\summer_program\imu\WIFI`. The serial project at
`D:\han_study\summer_program\imu\imu` and the BLE project at
`D:\han_study\summer_program\imu\BLE` remain unchanged.
