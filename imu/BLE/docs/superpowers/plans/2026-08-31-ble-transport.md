# BLE IMU Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent Windows BLE version of the single-node ESP32-S3 IMU system while preserving the current 11-column CSV data and browser visualization.

**Architecture:** The ESP32-S3 publishes newline-terminated CSV samples through a custom BLE GATT notify characteristic. A Bleak-based Python transport reassembles notification fragments into lines and feeds the existing parser, fusion, recording, and WebSocket pipeline; the page selects either USB serial or BLE.

**Tech Stack:** ESP32-S3 Arduino framework, PlatformIO, ESP32 Arduino BLE API, Python 3, Bleak, pyserial, FastAPI, WebSocket, vanilla JavaScript, unittest.

**Spec:** `docs/superpowers/specs/2026-08-31-ble-transport-design.md`

## Global Constraints

- Deliver the independent project to `D:\han_study\summer_program\imu\BLE`.
- Do not modify the existing `D:\han_study\summer_program\imu\imu` serial project.
- Advertise the ESP32-S3 as `IMU-MOTION-01`.
- Preserve the existing 11 numeric CSV columns and approximately 20 Hz sampling rate.
- Keep USB serial diagnostics enabled in BLE firmware.
- Only one computer transport may be active at a time.
- No pairing, authentication, multi-node synchronization, or binary payload in this version.
- Loss remains an arrival-gap estimate because the payload has no sequence number or device timestamp.

---

### Task 1: Create the isolated BLE project baseline

**Files:**
- Copy: serial project source into the BLE project, excluding `.pio/`, `recordings/`, `__pycache__/`, preview PNG files, and the staging directory
- Preserve: `docs/superpowers/specs/2026-08-31-ble-transport-design.md`
- Preserve: `docs/superpowers/plans/2026-08-31-ble-transport.md`

**Interfaces:**
- Consumes: the current serial project as a read-only baseline
- Produces: a self-contained BLE project with the existing tests initially passing

- [ ] **Step 1: Copy the baseline into a staging directory**

Copy `src/`, `dashboard/`, `web/`, `tests/`, `platformio.ini`, `requirements.txt`, `run_dashboard.py`, `README.md`, and `DASHBOARD.md` into `.ble-staging/`; retain the two BLE design documents already stored there.

- [ ] **Step 2: Verify the baseline Python and JavaScript tests**

Run:

```powershell
python -m unittest discover -s .ble-staging/tests -v
node --check .ble-staging/web/app.js
```

Expected: nine Python tests pass and Node exits with code 0.

- [ ] **Step 3: Verify project isolation**

Run:

```powershell
Get-FileHash src/main.cpp,.ble-staging/src/main.cpp
```

Expected: both hashes match before BLE changes begin.

### Task 2: Add tested BLE notification frame reassembly

**Files:**
- Create: `dashboard/ble_transport.py`
- Modify: `tests/test_dashboard.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `LineReassembler(max_bytes: int = 4096, stale_after: float = 1.0)`
- Produces: `LineReassembler.feed(data: bytes, now: float | None = None) -> tuple[list[bytes], int]`
- Produces: `BleDeviceInfo(address: str, name: str)`
- Produces: `scan_imu_devices(timeout: float = 5.0) -> list[BleDeviceInfo]`
- Produces: `BleTransport(device: str, on_line: Callable[[bytes], Awaitable[None]], on_disconnect: Callable[[str], Awaitable[None]])`

- [ ] **Step 1: Write failing fragment tests**

Add tests that assert:

```python
reassembler = LineReassembler(max_bytes=64, stale_after=1.0)
assert reassembler.feed(b"1,2,", now=0.0) == ([], 0)
assert reassembler.feed(b"3\n4,5,6\n", now=0.1) == ([b"1,2,3", b"4,5,6"], 0)
assert reassembler.feed(b"x" * 65, now=0.2) == ([], 1)
assert reassembler.feed(b"partial", now=1.0) == ([], 0)
assert reassembler.feed(b"next\n", now=2.1) == ([b"next"], 1)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```powershell
python -m unittest tests.test_dashboard.BleTransportTests -v
```

Expected: FAIL because `dashboard.ble_transport` does not exist.

- [ ] **Step 3: Implement the bounded reassembler**

Implement a byte buffer that extracts every `\n`-terminated line, strips a trailing `\r`, discards an over-limit partial line, and discards a stale partial line before accepting new data. Return the number of discarded partial frames so the runtime can increment `invalid_frames`.

- [ ] **Step 4: Implement Bleak scanning and connection wrappers**

Use `BleakScanner.discover(timeout=timeout)` and return devices whose name is exactly `IMU-MOTION-01`. Use `BleakClient(address, disconnected_callback=...)`, subscribe to the fixed notify UUID, feed notification bytes through `LineReassembler`, and call `on_line` once per complete line. Make `connect()`, `disconnect()`, and `is_connected` the only public connection controls.

- [ ] **Step 5: Add and install the dependency**

Append:

```text
bleak>=0.22,<2
```

to `requirements.txt`, then run:

```powershell
python -m pip install -r .ble-staging/requirements.txt
```

Expected: Bleak installs successfully.

- [ ] **Step 6: Run the focused and complete tests**

Run:

```powershell
python -m unittest tests.test_dashboard.BleTransportTests -v
python -m unittest discover -s .ble-staging/tests -v
```

Expected: fragment tests and all existing tests pass.

### Task 3: Refactor runtime transport selection

**Files:**
- Create: `dashboard/serial_transport.py`
- Modify: `dashboard/service.py`
- Modify: `dashboard/app.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Produces: `SerialTransport(port: str, baudrate: int, on_line, on_disconnect)` with `connect()`, `disconnect()`, and `is_connected`
- Runtime command: `{"action": "scan_devices", "transport": "ble"}`
- Runtime command: `{"action": "connect", "transport": "serial" | "ble", "device": str}`
- Payload fields: `stats.transport`, `stats.device`, `stats.serial_status` retained for page compatibility, and top-level `devices`

- [ ] **Step 1: Write failing runtime selection tests**

Use fake transport factories and assert that connecting BLE disconnects an active serial transport, a complete byte line reaches `CurrentCsvProtocol`, and a disconnect marks `right_wrist.valid` false. Assert that scan results appear as `[{"id": address, "name": "IMU-MOTION-01"}]`.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
python -m unittest tests.test_dashboard.TransportSelectionTests -v
```

Expected: FAIL because Runtime has no transport selection interface.

- [ ] **Step 3: Extract the existing pyserial loop**

Move serial open/read/close responsibility into `SerialTransport`. It passes non-empty raw lines to `on_line`; it does not parse CSV, update pose state, or broadcast UI messages.

- [ ] **Step 4: Route both transports through one runtime callback**

Add `Runtime.on_transport_line(raw: bytes)` that decodes UTF-8, calls `CurrentCsvProtocol.parse`, increments invalid counts on decoding or frame errors, and calls `consume` for valid samples. Keep fusion, quality, recording, and WebSocket broadcasting unchanged.

- [ ] **Step 5: Implement scanning and three-attempt BLE reconnect**

Scan only on explicit page command. On an unexpected BLE disconnect, mark the node offline and retry connection three times with delays of 1, 2, and 4 seconds. A user-requested disconnect cancels retries. Report the final exception text after the third failure.

- [ ] **Step 6: Extend status payload without removing compatibility fields**

Expose active `transport`, selected `device`, scan results, and connection message. Keep `serial_status` as the generic connection-state field so the existing page remains functional during the UI migration.

- [ ] **Step 7: Run all backend tests**

Run:

```powershell
python -m unittest discover -s .ble-staging/tests -v
```

Expected: all tests pass without physical BLE hardware.

### Task 4: Add ESP32-S3 BLE GATT notifications

**Files:**
- Modify: `src/main.cpp`
- Modify: `platformio.ini`

**Interfaces:**
- Advertised device: `IMU-MOTION-01`
- Custom service UUID: `7d2a0001-6c8a-4f6b-9c65-4f4d55494d55`
- Notify characteristic UUID: `7d2a0002-6c8a-4f6b-9c65-4f4d55494d55`
- Payload: current 11-column CSV plus `\n`

- [ ] **Step 1: Isolate CSV formatting from transport output**

Create `String formatSampleCsv(...)` returning exactly the existing 11 numeric columns without a header and without changing sensor units. Append `\n` only when transmitting.

- [ ] **Step 2: Initialize the BLE server**

Use the ESP32 Arduino BLE headers supplied by the framework. Create the custom service and notify characteristic, add the standard client configuration descriptor, advertise `IMU-MOTION-01`, and track connection state through server callbacks.

- [ ] **Step 3: Send robust notification chunks**

Request an MTU of 185 but send chunks no larger than the available negotiated payload; use a conservative 20-byte fallback. Send all chunks in order and preserve the final newline. Do nothing when no client is subscribed.

- [ ] **Step 4: Preserve USB diagnostics**

Print the same CSV line to USB serial and report BLE connect/disconnect events without mixing diagnostic text into BLE notifications.

- [ ] **Step 5: Compile firmware**

Run:

```powershell
pio run -d .ble-staging
```

Expected: firmware builds for `esp32-s3-devkitm-1` with no errors.

### Task 5: Add BLE device selection to the page

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Sends: `scan_devices`, `connect`, and `disconnect` commands defined in Task 3
- Consumes: `stats.transport`, `stats.device`, `stats.serial_status`, and `devices`

- [ ] **Step 1: Add transport and device controls**

Add a select with `USB串口` and `BLE`, a device select, and a `扫描设备` button. Default BLE display name is `IMU-MOTION-01`; retain COM21 as the serial default.

- [ ] **Step 2: Wire UI commands**

When BLE is selected, scanning sends `{"action":"scan_devices","transport":"ble"}`. Connecting sends the selected transport and device. Disable transport/device controls while connected, and restore them after disconnect or error.

- [ ] **Step 3: Update quality labels**

Show `BLE · IMU-MOTION-01` or `USB串口 · COM21` in the connection badge while preserving frame rate, estimated loss, invalid frames, and packet age.

- [ ] **Step 4: Check JavaScript syntax and run backend tests**

Run:

```powershell
node --check .ble-staging/web/app.js
python -m unittest discover -s .ble-staging/tests -v
```

Expected: Node exits 0 and all Python tests pass.

### Task 6: Perform hardware integration and comparison

**Files:**
- Modify: `README.md`
- Modify: `DASHBOARD.md`
- Create during testing: `recordings/ble-*` and `recordings/serial-*`

**Interfaces:**
- Consumes: compiled firmware and completed Windows receiver
- Produces: reproducible connection instructions and serial-versus-BLE observations

- [ ] **Step 1: Flash the BLE firmware**

Run with the detected ESP32-S3 port:

```powershell
pio run -d .ble-staging -t upload --upload-port COM21
```

Expected: upload completes and USB logs continue at 115200 baud.

- [ ] **Step 2: Verify Windows discovery and live data**

Start `python .ble-staging/run_dashboard.py`, open `http://127.0.0.1:8000`, select BLE, scan, select `IMU-MOTION-01`, and connect. Expected: right wrist becomes online and observed frame rate approaches 20 Hz.

- [ ] **Step 3: Verify disconnect recovery**

Power-cycle the sensor once. Expected: the page marks the node offline, the backend attempts reconnect up to three times, and live data resumes if the device returns during those attempts.

- [ ] **Step 4: Record matched ten-minute trials**

Record ten minutes over USB serial and ten minutes over BLE using the same sample rate and comparable movements. Export both sessions and compare average observed frame rate, estimated loss, invalid frames, interval jitter, and disconnect count.

- [ ] **Step 5: Document exact operating steps and limitations**

Update the README with dependency installation, firmware build/upload, Windows Bluetooth requirements, scan/connect instructions, the UUIDs, and the limitation that loss and latency are not exact without sequence numbers and device timestamps.

### Task 7: Deliver the isolated BLE directory

**Files:**
- Deliver: `D:\han_study\summer_program\imu\BLE`

**Interfaces:**
- Consumes: verified `.ble-staging` project
- Produces: the requested standalone BLE project without modifying the serial project

- [ ] **Step 1: Re-run non-hardware verification**

Run:

```powershell
python -m unittest discover -s .ble-staging/tests -v
node --check .ble-staging/web/app.js
pio run -d .ble-staging
```

Expected: all tests and build pass.

- [ ] **Step 2: Verify the destination is the intended empty folder**

Resolve `D:\han_study\summer_program\imu\BLE` and confirm it is not the existing serial project and contains no user files before copying.

- [ ] **Step 3: Copy the verified project to the destination**

Copy the staging project to `D:\han_study\summer_program\imu\BLE`, excluding `.pio`, `__pycache__`, and generated recordings unless the comparison recordings are explicitly requested.

- [ ] **Step 4: Verify delivered files**

Run the Python tests and JavaScript syntax check from the delivered directory and confirm the original serial project's `src/main.cpp`, `dashboard/service.py`, and `web/app.js` hashes are unchanged.
