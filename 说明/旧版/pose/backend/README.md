> **旧版参考资料**：适用于旧版 `旧版/IMU-tracker/`、`旧版/pose/` 和 `旧版/contracts/`，不代表当前 `源代码/` 的配置或验收状态。

# Motion-capture backend

This Python service owns transport decoding, raw recording/replay, sensor calibration,
orientation fusion, multi-node synchronization, skeleton kinematics and the WebSocket API.
The browser intentionally receives only versioned pose and skeleton messages.

## Quick start

```powershell
cd 旧版/pose/backend
uv sync --extra dev
uv run mocap-server --source mock
```

Open the frontend separately and connect it to `ws://127.0.0.1:8000/ws/pose`.
Use `--source serial --port COM5`, `--source ble`, or `--source replay --path <session>`
when the corresponding hardware or recording is available.

The wire contract is owned by `../../contracts/`. Runtime recordings and personal
calibrations are generated outside this package and are not committed.

`/ws/pose` samples only the latest pose for node 1 at at most 60 Hz, so 14 x 100 Hz
sensor traffic never becomes browser message traffic. Select another diagnostic node
with `/ws/pose?node_id=2`. `/ws/skeleton` publishes the synchronized full skeleton at
the configured render rate.

## Implementation status

The protocol, Golden Vector, BLE fragment reassembly, raw batch expansion, replay,
fusion, clock fitting, bounded reordering, 14-node kinematics and Mock WebSocket path
are covered by automated tests. USB serial and BLE hardware paths require their M4/M6
bench acceptance tests before being treated as production-ready.

The recording CLI writes real raw sessions. The HTTP control endpoints currently
provide the frontend's deterministic control/status flow; mounting calibration and
record/playback orchestration remain operator-driven through the corresponding CLI
commands until hardware sessions are available. OTA and firmware power policy belong
to `IMU-tracker`, not this backend.
