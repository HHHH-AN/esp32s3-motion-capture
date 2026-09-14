# Windows BLE IMU Transport Design

## Goal

Create an independent BLE version of the existing single-node IMU project in
`D:\han_study\summer_program\imu\BLE`. Keep the current USB serial project
unchanged so the two transports can be tested and compared with the same
sensor sampling, CSV parsing, pose fusion, recording, and visualization logic.

## Scope

- One real IMU node (right wrist) and the existing simulated body nodes.
- ESP32-S3 BLE, because ESP32-S3 does not support Bluetooth Classic SPP.
- Windows computer receiver and the existing browser visualization.
- Preserve the current 11-column, approximately 20 Hz CSV payload.
- Compare BLE against USB serial; do not receive both simultaneously.
- No pairing, authentication, multi-node synchronization, or binary protocol
  in the first version.

## Architecture

```text
ICM-42688 + LIS2MDL
        |
     ESP32-S3
        |
 BLE GATT Notify
        |
Python/Bleak receiver on Windows
        |
existing CSV parser and pose pipeline
        |
WebSocket -> browser visualization
```

The BLE firmware advertises as `IMU-MOTION-01`. It exposes a custom GATT
service and a notify characteristic. Each sample uses the same 11 numeric CSV
columns as the serial version and ends with `\n`.

The Windows receiver subscribes to notifications, appends notification bytes
to a bounded buffer, and extracts complete newline-terminated frames. This
works whether one CSV line arrives in one notification or is fragmented by the
negotiated BLE MTU.

## Firmware

- Keep USB serial logging available for diagnostics.
- Sample the sensors and format one CSV line every 50 ms.
- Send that line through the notify characteristic when a BLE client is
  subscribed.
- Split a line when necessary instead of assuming a particular MTU.
- Do not block sensor sampling while no BLE client is connected.
- Use fixed service and characteristic UUIDs documented in the source.

## Windows Receiver

Add a Bleak-based transport alongside the existing pyserial transport. Both
transports feed complete text lines into the same `CurrentCsvProtocol` and the
same `Runtime.consume` method.

The BLE transport supports scanning for `IMU-MOTION-01`, connecting,
subscribing, disconnecting, bounded frame reassembly, and up to three automatic
reconnection attempts. A failed reconnect leaves the node offline and reports
a clear status to the page.

## User Interface

Add a transport selector and device selector near the existing connection
button:

- `USB串口` with a COM port.
- `BLE` with a discovered device named `IMU-MOTION-01`.

The quality panel displays the active transport, device, connection state,
valid and invalid frames, observed frame rate, estimated loss, and packet age.
Only one transport can be active at a time.

## Quality Metrics

The first BLE version deliberately preserves the original payload. Since that
payload has neither a sequence number nor a device timestamp, loss remains an
estimate based on arrival gaps and true end-to-end latency cannot be measured.
The comparison will cover:

- observed frame rate;
- estimated loss rate;
- invalid frame count;
- inter-arrival jitter;
- disconnect and reconnect behavior;
- ten-minute stability.

A later protocol can add sequence numbers and device timestamps if the initial
BLE comparison justifies it.

## Error Handling

- A scan timeout reports that no matching BLE device was found.
- Disconnect marks the real node offline immediately.
- Incomplete fragments remain buffered until a newline arrives.
- An overlong or stale partial frame is discarded and counted as invalid.
- The receive buffer has a fixed upper bound.
- BLE failures do not disable USB serial diagnostics.

## Verification

1. Firmware advertises `IMU-MOTION-01` and Windows can discover it.
2. Windows connects and receives approximately 20 valid 11-column frames per
   second.
3. Fragmented and combined notifications reconstruct frames correctly.
4. A disconnect updates the UI and reconnection succeeds when the device is
   available again.
5. A ten-minute run does not crash or grow the receive buffer without bound.
6. Serial and BLE recordings from equivalent motion can be compared using the
   same dashboard metrics.

## Project Isolation

Implementation is assembled separately and delivered to
`D:\han_study\summer_program\imu\BLE`. The existing
`D:\han_study\summer_program\imu\imu` serial project remains unchanged.
