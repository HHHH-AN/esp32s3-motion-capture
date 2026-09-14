# Wi-Fi TCP IMU Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent Windows Wi-Fi/TCP version of the single-node ESP32-S3 IMU system while preserving the existing 11-column CSV and visualization pipeline.

**Architecture:** ESP32-S3 joins the same router as the computer, obtains a DHCP address, and serves newline-terminated CSV on TCP port 9000. An asyncio Python transport reconnects and feeds complete lines into the existing parser, fusion, recording, and WebSocket pipeline; the page switches between USB serial and Wi-Fi endpoints.

**Tech Stack:** ESP32-S3 Arduino WiFi library, PlatformIO, Python asyncio, pyserial, FastAPI, WebSocket, vanilla JavaScript, unittest.

**Spec:** `docs/superpowers/specs/2026-08-31-wifi-tcp-transport-design.md`

## Global Constraints

- Deliver to `D:\han_study\summer_program\imu\WIFI`.
- Do not modify the serial project or BLE project.
- Wi-Fi mode is station mode on the same router as the Windows computer.
- TCP port defaults to 9000 and accepts one client.
- Preserve the 11-column CSV and approximately 20 Hz sampling.
- Keep USB serial diagnostics and CSV output active.
- Only one computer transport may be active at a time.
- Credentials live in ignored `include/wifi_config.h`; the example contains no real password.
- Do not claim exact radio loss or latency from TCP and the current payload.

---

### Task 1: Establish an isolated baseline

**Files:**
- Copy: `src/`, `dashboard/`, `web/`, `tests/`, `include/`, project configuration, launchers, and documentation into `.wifi-staging/`
- Preserve: the Wi-Fi spec and plan

**Interfaces:**
- Consumes: current serial project as read-only baseline
- Produces: isolated project with baseline tests passing

- [ ] Copy source files while excluding `.pio`, `.platformio-core`, recordings, caches, preview images, and other staging folders.
- [ ] Run `python -m unittest discover -s tests -v` from staging; expect nine baseline tests to pass.
- [ ] Run `node --check web/app.js`; expect exit code 0.
- [ ] Record SHA-256 hashes of the original `src/main.cpp`, `dashboard/service.py`, and `web/app.js` for final isolation verification.

### Task 2: Implement tested TCP line reception

**Files:**
- Create: `dashboard/tcp_transport.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Produces: `LineReassembler(max_bytes: int = 4096, stale_after: float = 1.0)`
- Produces: `LineReassembler.feed(data: bytes, now: float | None = None) -> tuple[list[bytes], int]`
- Produces: `TcpTransport(host: str, port: int, on_line, on_disconnect, connect_timeout: float = 5.0)`
- Produces: async `connect()`, `disconnect()`, and `is_connected`

- [ ] Add tests where `b"1,2,"` followed by `b"3\n4,5,6\n"` produces two complete lines.
- [ ] Add tests where a 4097-byte partial frame and a partial frame older than one second are discarded and counted.
- [ ] Run `python -m unittest tests.test_dashboard.TcpTransportTests -v`; expect import failure before implementation.
- [ ] Implement bounded reassembly, `asyncio.open_connection`, a background `reader.read(1024)` loop, five-second connection timeout, zero-read disconnect, and clean writer shutdown.
- [ ] Re-run the focused and complete test suites; expect all tests to pass.

### Task 3: Add serial/TCP runtime selection

**Files:**
- Create: `dashboard/serial_transport.py`
- Modify: `dashboard/service.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Runtime command: `{"action":"connect","transport":"wifi","host":"192.168.1.120","port":9000}`
- Runtime command: `{"action":"connect","transport":"serial","device":"COM21"}`
- Payload: `stats.transport`, `stats.device`, `stats.host`, `stats.tcp_port`, and existing `stats.serial_status`

- [ ] Add fake-transport tests proving a TCP line passes through `CurrentCsvProtocol`, invalid lines increment `invalid_frames`, and a disconnect marks `right_wrist` offline.
- [ ] Extract the pyserial read loop into `SerialTransport`, leaving parsing in Runtime.
- [ ] Add endpoint validation with `ipaddress.ip_address` or a hostname containing only letters, digits, dots, and hyphens; require port 1 through 65535.
- [ ] Route both transports through `Runtime.on_transport_line(raw: bytes)`.
- [ ] On unexpected TCP disconnect, retry after 1, 2, and 4 seconds; cancel retries on user disconnect.
- [ ] Preserve existing recording, fusion, quality, and WebSocket behavior.
- [ ] Run all Python tests; expect all to pass without hardware.

### Task 4: Implement ESP32-S3 Wi-Fi/TCP firmware

**Files:**
- Modify: `src/main.cpp`
- Create: `include/wifi_config.h`
- Create: `include/wifi_config.example.h`
- Modify: `.gitignore`

**Interfaces:**
- Configuration macros: `WIFI_SSID`, `WIFI_PASSWORD`, `WIFI_TCP_PORT`
- TCP payload: original 11 numeric CSV columns plus newline
- Serial status: `[WiFi] Connected`, `[WiFi] IP: ...`, `[TCP] Listening on port 9000`

- [ ] Add compile-safe configuration files with empty local credentials and port 9000; ignore only `include/wifi_config.h`.
- [ ] Refactor sample formatting into one `char line[256]` used by serial and TCP.
- [ ] Add non-blocking station connection management with a five-second retry interval.
- [ ] Start `WiFiServer` only while Wi-Fi is connected, accept one client, and return to listening when it disconnects.
- [ ] Send every complete sample to the active TCP client without blocking sensor sampling when no client exists.
- [ ] Compile using PlatformIO; expect successful ESP32-S3 firmware build.

### Task 5: Add Wi-Fi controls to the dashboard

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: runtime fields and commands from Task 3
- Produces: transport select, host input, port input, and connection controls

- [ ] Add `USB串口` and `Wi-Fi` transport choices, host default `192.168.1.120`, and port default `9000`.
- [ ] Send serial or Wi-Fi connection parameters according to the selected transport.
- [ ] Disable endpoint controls while connected and restore them after disconnect/error.
- [ ] Display `Wi-Fi · host:port` or `USB串口 · COM21` in the quality badge.
- [ ] Run Node syntax checking and all Python tests; expect success.

### Task 6: Document, verify, and deliver

**Files:**
- Create: `WIFI_README.md`
- Deliver: `D:\han_study\summer_program\imu\WIFI`

**Interfaces:**
- Produces: standalone, buildable Wi-Fi project and operating instructions

- [ ] Document credential editing, firmware build/upload, serial IP discovery, dashboard startup, endpoint entry, and TCP measurement limitations.
- [ ] Run all Python tests, JavaScript syntax checking, and PlatformIO build from staging.
- [ ] Start the dashboard on a temporary port and verify `/api/status` contains Wi-Fi fields and `/` contains the new controls.
- [ ] Confirm the destination resolves exactly to `D:\han_study\summer_program\imu\WIFI` and is empty before delivery.
- [ ] Copy the verified project while excluding build products, recordings, caches, and toolchains.
- [ ] Re-run Python and JavaScript verification from the delivered folder.
- [ ] Confirm original serial and BLE project hashes remain unchanged.
