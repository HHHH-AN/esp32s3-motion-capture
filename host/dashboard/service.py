from __future__ import annotations

import asyncio
import csv
import json
import math
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from time import monotonic, time
from typing import Any, TextIO
from uuid import uuid4

from .tcp_transport import TcpTransport
from .fusion import ComplementaryFusion, euler_degrees, relative
from .coordinates import CoordinateSettings
from .motion import DisplacementEstimator
from .models import SensorSample, initial_nodes
from .protocol import CurrentCsvProtocol, FrameError
from .serial_transport import SerialTransport

DATA_HEADER = ["时间戳", "节点名称", "节点ID", "数据来源", "有效", "四元数W", "四元数X", "四元数Y", "四元数Z",
               "加速度X", "加速度Y", "加速度Z", "角速度X", "角速度Y", "角速度Z",
               "磁场X", "磁场Y", "磁场Z", "ICM温度", "LIS温度原始值"]
TRAJECTORY_HEADER = ["时间戳", "轨迹类型", "节点名称", "节点ID", "位置X米", "位置Y米", "位置Z米", "说明"]
DATA_HEADER += ["帧序号", "设备采样微秒", "传感器状态", "接收单调时间", "Roll度", "Pitch度", "Yaw度"]
DATA_HEADER += [f"位移{k}米" for k in "XYZ"] + [f"速度{k}米每秒" for k in "XYZ"]
DATA_HEADER += [f"线性加速度{k}米每秒平方" for k in "XYZ"] + ["位移估算阶段", "位移估算秒"]
DATA_HEADER += [f"原始{sensor}{axis}" for sensor in ("加速度", "角速度", "磁场") for axis in "XYZ"]
DATA_HEADER += ["静止修正启用", "静止检测确认", "速度归零次数"]


@dataclass
class Runtime:
    port: str = "COM9"
    baudrate: int = 115200
    transport: str = "wifi"
    device: str = "192.168.4.1:9000"
    host: str = "192.168.4.1"
    tcp_port: int = 9000
    expected_rate: float = 20.0
    nodes: dict = field(default_factory=initial_nodes)
    status: str = "disconnected"
    message: str = "等待连接设备"
    valid_frames: int = 0
    invalid_frames: int = 0
    estimated_lost: int = 0
    latest_at: float | None = None
    latest_unix: float | None = None
    recording: bool = False
    record_path: str | None = None
    record_rows: int = 0
    selected_record_node: str = "right_wrist"
    recording_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "recordings")
    coordinate_file: Path | None = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "coordinate_settings.json")

    def __post_init__(self) -> None:
        self.protocol = CurrentCsvProtocol()
        self.fusion = ComplementaryFusion()
        self.motion = DisplacementEstimator()
        self.coordinates = CoordinateSettings()
        if self.coordinate_file and self.coordinate_file.exists():
            try:
                self.coordinates = CoordinateSettings.parse(json.loads(self.coordinate_file.read_text(encoding="utf-8")))
            except (ValueError, OSError, TypeError):
                self.message = "坐标配置无法读取，已使用默认右手系"
        self._arrival_times: deque[float] = deque()
        self._previous_arrival: float | None = None
        self._transport = None
        self._user_disconnecting = False
        self._connection_generation = 0
        self._record_started: float | None = None
        self._record_files: dict[str, TextIO] = {}
        self._writers: dict[str, csv.writer] = {}
        self.clients: set[Any] = set()
        self._heartbeat_task = None
        self._operation_lock = asyncio.Lock()
        self._broadcast_lock = asyncio.Lock()
        self._last_sequence = None
        self._last_device_us = None
        self._node_id = None
        self._origin = (1.0, 0.0, 0.0, 0.0)
        self._gyro_bias = (0.0, 0.0, 0.0)
        self._calibration = None
        self.calibration_message = "未进行软件零偏校准"
        self._sensor_flags = 0
        self._sequence_mode = False
        self.duplicate_frames = 0
        self.device_restarts = 0
        self._raw_sample = None
        self._peak_gyro = 0.0
        self._pose_epoch = 0

    async def start(self) -> None:
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def close(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        await self.disconnect()
        self.stop_recording()

    async def _heartbeat(self) -> None:
        while True:
            await self.broadcast()
            await asyncio.sleep(.05)

    async def connect(self, port: str | None = None, transport: str | None = None,
                      device: str | None = None, host: str | None = None,
                      tcp_port: int | None = None) -> None:
        selected_transport = transport or self.transport
        selected_device = device or port or self.port
        if selected_transport not in {"serial", "wifi"}:
            self.status, self.message = "error", f"不支持的通信方式: {selected_transport}"
            await self.broadcast()
            return
        await self.disconnect()
        self.transport, self.device = selected_transport, selected_device
        if selected_transport == "serial":
            self.port = selected_device
        else:
            try:
                self.host = str(self.host if host is None else host).strip()
                self.tcp_port = int(self.tcp_port if tcp_port is None else tcp_port)
            except (TypeError, ValueError):
                self.status, self.message = "error", "Wi-Fi地址或端口无效"
                return
            selected_device = f"{self.host}:{self.tcp_port}"
            self.device = selected_device
            if not self._valid_endpoint(self.host, self.tcp_port):
                self.status, self.message = "error", "Wi-Fi地址或端口无效"
                await self.broadcast()
                return
        self.status, self.message = "connecting", f"正在连接 {selected_device}"
        self._user_disconnecting = False
        self._last_sequence = self._last_device_us = None
        self._node_id = None
        self._origin = (1.0, 0.0, 0.0, 0.0)
        self._gyro_bias = (0.0, 0.0, 0.0)
        self.valid_frames = self.invalid_frames = self.estimated_lost = 0
        self.duplicate_frames = self.device_restarts = 0
        self._arrival_times.clear()
        self.latest_at = self.latest_unix = None
        self._sensor_flags = 0
        self._sequence_mode = False
        self._peak_gyro = 0.0
        self.fusion.reset()
        self.motion.reset()
        self.calibration_message = "未进行软件零偏校准"
        self._previous_arrival = None
        self._calibration = None
        self.fusion.last_time = self.fusion.last_device_us = None
        await self.broadcast()
        try:
            self._transport = self._new_transport()
            await self._transport.connect()
            self.status, self.message = "connected", f"已连接 {selected_device}"
            self.motion.start(0, True, "balanced")
            self._pose_epoch += 1
        except Exception as exc:
            # Keep a transport whose driver open/cleanup may still be pending;
            # a subsequent connect must finish disconnecting it first.
            detail = str(exc)
            if not detail:
                detail = f"连接 {selected_device} 超时" if isinstance(exc, TimeoutError) else type(exc).__name__
            if self.transport == "serial" and ("PermissionError" in detail or "Access is denied" in detail):
                detail = f"串口 {self.port} 被占用，请关闭 PlatformIO/Arduino 串口监视器后重试"
            self.status, self.message = "error", detail
            self.nodes["right_wrist"].valid = False
        await self.broadcast()

    async def disconnect(self) -> None:
        self._user_disconnecting = True
        self._connection_generation += 1
        self._calibration = None
        self.stop_recording()
        self.motion.stop("连接已断开，位移估算结束")
        active, self._transport = self._transport, None
        try:
            if active:
                await active.disconnect()
        except Exception as exc:
            self._transport = active
            self.status, self.message = "error", str(exc) or type(exc).__name__
            self.nodes["right_wrist"].valid = False
            await self.broadcast()
            raise
        self.status, self.message = "disconnected", "设备已断开"
        self.nodes["right_wrist"].valid = False
        await self.broadcast()

    def _new_transport(self):
        generation = self._connection_generation

        async def line(raw):
            if generation == self._connection_generation and not self._user_disconnecting:
                await self.on_transport_line(raw)

        async def disconnected(reason):
            if generation == self._connection_generation:
                await self._transport_disconnected(reason)

        if self.transport == "wifi":
            return TcpTransport(self.host, self.tcp_port, line, disconnected)
        return SerialTransport(self.port, self.baudrate, line, disconnected)

    @staticmethod
    def _valid_endpoint(host: str, port: int) -> bool:
        return bool(host) and 1 <= port <= 65535 and all(
            char.isalnum() or char in ".-:" for char in host)

    async def on_transport_line(self, raw: bytes) -> None:
        try:
            sample = self.protocol.parse(raw.decode("utf-8"))
            if sample is not None:
                await self.consume(sample)
        except (FrameError, UnicodeDecodeError):
            self.invalid_frames += 1
            if self._heartbeat_task is None:
                await self.broadcast()

    async def _transport_disconnected(self, reason: str) -> None:
        generation = self._connection_generation
        self.nodes["right_wrist"].valid = False
        self._calibration = None
        self.motion.stop("数据连接中断，位移估算结束")
        if self._user_disconnecting:
            return
        if self.transport != "wifi":
            self.status, self.message = "error", reason
            await self.broadcast()
            return
        for attempt, delay in enumerate((1, 2, 4), start=1):
            self.status, self.message = "connecting", f"Wi-Fi已断开，正在重连 {attempt}/3"
            await self.broadcast()
            await asyncio.sleep(delay)
            if self._user_disconnecting or generation != self._connection_generation:
                return
            try:
                candidate = self._new_transport()
                self._transport = candidate
                await candidate.connect()
                if self._user_disconnecting or generation != self._connection_generation:
                    await candidate.disconnect()
                    return
                self.status, self.message = "connected", f"已重新连接 {self.device}"
                await self.broadcast()
                return
            except Exception as exc:
                reason = str(exc)
        self._transport = None
        self.status, self.message = "error", f"Wi-Fi重连失败: {reason}"
        await self.broadcast()

    def _update_quality(self, arrival: float, estimate: bool = True) -> None:
        if estimate and self._previous_arrival is not None:
            gap = arrival - self._previous_arrival
            if gap <= 2.0:
                self.estimated_lost += max(0, round(gap * self.expected_rate) - 1)
        self._previous_arrival = arrival
        self._arrival_times.append(arrival)
        while self._arrival_times and arrival - self._arrival_times[0] > 2.0:
            self._arrival_times.popleft()

    async def consume(self, sample: SensorSample) -> None:
        if not sample.sensor_flags & 1:
            self.invalid_frames += 1
            return
        if self._node_id is not None and self._node_id != sample.node_id:
            self.invalid_frames += 1
            self.message = "单节点模式拒绝混入其他节点的数据"
            return
        self._node_id = sample.node_id
        self._sequence_mode = sample.sequence is not None
        if sample.sequence is not None and self._last_sequence is not None:
            delta = (sample.sequence - self._last_sequence) % 2**32
            if delta == 0:
                self.duplicate_frames += 1
                return
            if delta >= 2**31:
                self.device_restarts += 1
                self._calibration = None
                self.fusion.reset()
                self.motion.stop("设备重启，位移估算结束")
                self._origin = (1.0, 0.0, 0.0, 0.0)
            else:
                self.estimated_lost += delta - 1
        self._last_sequence, self._last_device_us = sample.sequence, sample.device_us
        self._sensor_flags = sample.sensor_flags
        self._raw_sample = sample
        self._update_calibration(sample)
        mapped = self.coordinates.sample(sample)
        corrected = self.coordinates.sample(replace(sample, gyro=tuple(v-b for v, b in zip(sample.gyro, self._gyro_bias))))
        node = self.nodes["right_wrist"]
        correction_scale = .05 if self.motion.phase == "measuring" and not self.motion.stationary else 1.0
        node.quaternion = relative(self.fusion.update(corrected, correction_scale), self._origin)
        node.accel, node.gyro, node.mag = mapped.accel, mapped.gyro, mapped.mag
        node.temperature, node.aux_temperature = sample.temperature, sample.aux_temperature
        node.updated_at, node.valid = sample.received_unix, True
        self.valid_frames += 1
        self.latest_at, self.latest_unix = sample.received_monotonic, sample.received_unix
        self._update_quality(sample.received_monotonic, estimate=not self._sequence_mode)
        self._peak_gyro = max(self._peak_gyro, math.sqrt(sum(v*v for v in corrected.gyro)))
        self.motion.update(corrected, self.fusion.q)  # Gravity removal uses absolute, never zeroed display attitude.
        self._record(sample.received_unix)
        if self._heartbeat_task is None:
            await self.broadcast(self.payload())

    def _update_calibration(self, sample: SensorSample) -> None:
        if self._calibration is None:
            return
        norm = math.sqrt(sum(v*v for v in sample.accel))
        if not .85 <= norm <= 1.15 or max(abs(v) for v in sample.gyro) > 5:
            self._calibration = None
            self.calibration_message = "校准取消：检测到运动，请静置板子后重试"
            return
        state = self._calibration
        if state["start"] is None:
            state["start"] = sample.received_monotonic
        state["count"] += 1
        state["sum"] = [a+b for a, b in zip(state["sum"], sample.gyro)]
        elapsed = sample.received_monotonic - state["start"]
        self.calibration_message = f"静置校准中 {min(elapsed, 3):.1f}/3 秒"
        if elapsed >= 3 and state["count"] >= 30:
            self._gyro_bias = tuple(v/state["count"] for v in state["sum"])
            self._calibration = None
            self.calibration_message = "零偏校准完成（仅当前运行有效）"
            self.fusion.reset()
            self._origin = (1.0, 0.0, 0.0, 0.0)
            self.motion.start(0, True, "balanced")
            self._pose_epoch += 1

    def quality(self) -> dict:
        now = monotonic()
        while self._arrival_times and now - self._arrival_times[0] > 2.0:
            self._arrival_times.popleft()
        rate = 0.0
        if len(self._arrival_times) > 1:
            span = self._arrival_times[-1] - self._arrival_times[0]
            rate = (len(self._arrival_times) - 1) / span if span > 0 else 0.0
        expected = self.valid_frames + self.estimated_lost
        return {"frame_rate": round(rate, 1),
                "estimated_loss_rate": round(self.estimated_lost / expected * 100, 2) if expected else 0.0,
                "packet_age_ms": None if self.latest_at is None else round((now - self.latest_at) * 1000)}

    def payload(self) -> dict:
        if self.latest_at is not None and monotonic() - self.latest_at > 1.5:
            self.nodes["right_wrist"].valid = False
            self.motion.stop("数据超时，位移估算结束")
        motion = self.motion.payload(self.coordinates, self._origin)
        node_payloads = []
        for node in self.nodes.values():
            if node.source != "real":
                continue
            item = node.payload()
            item["node_id"] = self._node_id or "right_wrist"
            item["euler"] = euler_degrees(node.quaternion)
            item["position"] = motion["position"]
            node_payloads.append(item)
        quality = self.quality()
        return {"version": 2, "type": "frame", "timestamp": time(), "latest_packet_at": self.latest_unix,
                "nodes": node_payloads,
                "coordinates": self.coordinates.payload(), "motion": motion,
                "pose": {"position":motion["position"],
                         "quaternion":self.nodes["right_wrist"].quaternion,
                         "axis_signs":self.coordinates.displacement_signs,"epoch":self._pose_epoch},
                "trajectory": {"body": motion["position"], "selected_node": self.selected_record_node},
                "stats": {"serial_status": self.status, "message": self.message, "port": self.port,
                          "transport": self.transport, "device": self.device,
                          "host": self.host, "tcp_port": self.tcp_port,
                          "valid_frames": self.valid_frames, "invalid_frames": self.invalid_frames,
                          "sequence": self._last_sequence, "device_us": self._last_device_us,
                          "loss_method": "sequence" if self._sequence_mode else "arrival_estimate",
                          "sensor_flags": self._sensor_flags, "duplicate_frames": self.duplicate_frames,
                          "device_restarts": self.device_restarts, "peak_gyro_dps": round(self._peak_gyro, 2),
                          "gyro_bias": self.coordinates.sensor_vector(self._gyro_bias), "calibrating": self._calibration is not None,
                          "calibration_message": self.calibration_message,
                          "estimated_lost": self.estimated_lost, **quality,
                          "recording": self.recording, "record_path": self.record_path,
                          "record_rows": self.record_rows,
                          "record_duration_s": round(monotonic() - self._record_started, 1) if self._record_started else 0}}

    async def broadcast(self, payload: dict | None = None) -> None:
        async with self._broadcast_lock:
            await self._broadcast(payload)

    async def _broadcast(self, payload: dict | None = None) -> None:
        if not self.clients:
            return
        message = json.dumps(payload or self.payload(), ensure_ascii=False)
        stale = []
        for client in tuple(self.clients):
            try:
                await asyncio.wait_for(client.send_text(message), timeout=.5)
            except Exception:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)
            try:
                await asyncio.wait_for(client.close(), timeout=.5)
            except Exception:
                pass

    async def command(self, data: dict) -> None:
        if not isinstance(data, dict):
            self.message = "命令应为 JSON 对象"
            return
        async with self._operation_lock:
            try:
                await self._command(data)
            except (ValueError, TypeError, OSError, KeyError) as exc:
                self.message = f"操作失败: {exc}"
            await self.broadcast()

    async def _command(self, data: dict) -> None:
        self.payload()  # Apply age-based invalidation before accepting calibration/zero commands.
        action = data.get("action")
        if action == "connect":
            await self.connect(data.get("port"), data.get("transport"), data.get("device"),
                               data.get("host"), data.get("tcp_port"))
        elif action == "disconnect":
            await self.disconnect()
        elif action == "zero":
            if self.recording:
                raise ValueError("请先停止记录再改变参考姿态")
            if not self.nodes["right_wrist"].valid:
                raise ValueError("请先连接并接收到实时数据")
            self._origin = self.fusion.q
            self.nodes["right_wrist"].quaternion = (1.0, 0.0, 0.0, 0.0)
            self.motion.start(0, True, self.motion.drift_mode)
            self._pose_epoch += 1
            self.message = "已设置三维参考位姿；请静置初始化，当前位置作为原点"
        elif action == "calibrate":
            if self.recording:
                raise ValueError("请先停止记录再校准")
            if not self.nodes["right_wrist"].valid:
                raise ValueError("请先连接并接收到实时数据")
            self._calibration = {"start": None, "count": 0, "sum": [0.0, 0.0, 0.0]}
            self.motion.stop("零偏校准开始，位移估算已停止")
            self.calibration_message = "请保持板子静止至少 3 秒"
        elif action == "set_coordinates":
            if self.recording or self._calibration is not None:
                raise ValueError("请先停止记录并等待校准结束，再调整坐标")
            coordinates = CoordinateSettings.parse(data.get("coordinates"))
            if self.coordinate_file:
                pending = self.coordinate_file.with_suffix(".tmp")
                pending.write_text(json.dumps(coordinates.payload(), ensure_ascii=False, indent=2), encoding="utf-8")
                pending.replace(self.coordinate_file)
            self.coordinates = coordinates
            self.fusion.reset()
            self._origin = (1.0, 0.0, 0.0, 0.0)
            self.motion.reset()
            if self.nodes["right_wrist"].valid:
                self.motion.start(0, True, "balanced")
            self._pose_epoch += 1
            self.nodes["right_wrist"].valid = False
            self.message = "坐标设置已保存；姿态参考和位移估算已重置"
        elif action == "start_motion":
            if self.recording:
                raise ValueError("请先停止记录，开始位移估算后再记录")
            if not self.nodes["right_wrist"].valid or self._calibration is not None:
                raise ValueError("请先连接并等待零偏校准完成")
            self.motion.start(data.get("duration_s", 0), data.get("zupt", True), data.get("drift_mode","balanced"), preserve_position=True)
        elif action == "stop_motion":
            self.motion.stop()
        elif action == "reset_motion":
            if self.recording:
                raise ValueError("请先停止记录再重置位移")
            self.motion.reset()
            self._pose_epoch += 1
            if self.nodes["right_wrist"].valid:
                self.motion.start(0, True, "balanced")
        elif action == "start_recording":
            self.selected_record_node = "right_wrist"
            self.start_recording()
        elif action == "stop_recording":
            self.stop_recording()
        elif action == "select_record_node" and data.get("node_id") in self.nodes:
            self.selected_record_node = data["node_id"]
        await self.broadcast()

    def start_recording(self) -> None:
        if self.recording:
            return
        if self._calibration is not None:
            raise ValueError("请等待校准完成再记录")
        if self.motion.phase == "initializing":
            raise ValueError("请等待位移静置初始化完成再记录")
        folder = self.recording_dir / f"imu-{datetime.now():%Y%m%d-%H%M%S-%f}-{uuid4().hex[:8]}"
        folder.mkdir(parents=True, exist_ok=False)
        files = {"data": folder / "imu-data.csv"}
        for key, path in files.items():
            handle = path.open("w", encoding="utf-8-sig", newline="")
            self._record_files[key] = handle; self._writers[key] = csv.writer(handle)
        self._writers["data"].writerow(DATA_HEADER)
        (folder / "metadata.json").write_text(json.dumps({
            "version": 2, "transport": self.transport, "device": self.device,
            "units": {"accel": "g", "gyro": "deg/s", "mag": "mG", "device_us": "us"},
            "gyro_bias_dps": self._gyro_bias, "reference_quaternion": self._origin,
            "coordinates": self.coordinates.payload(),
            "displacement": {"method":"gravity removal + trapezoidal integration", "approximate":True,
                             "frame":"reference quaternion frame; user output signs", "duration_s":self.motion.duration,
                             "drift_mode":self.motion.drift_mode,"zupt":self.motion.zupt,
                             "accel_reference_g":self.motion.accel_reference_g,
                             "bias_model":"static magnitude normalisation only; no 3D bias calibration",
                             "rest_detector":{"frame":"sensor", "window_s":.3,
                                              "accel_std_g":.006,"gyro_peak_dps":1.5,
                                              "norm_tolerance_g":.06}},
            "node_id": self._node_id,
            "pose_note": "位置与姿态为同一参考坐标；显示镜像作用于模型几何和位置，不修改内部重力补偿",
            "attitude_correction_scale_moving": .05
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.recording, self.record_path, self.record_rows = True, str(folder), 0
        self._record_started = monotonic()

    def _record(self, timestamp: float) -> None:
        if not self.recording:
            return
        for node in self.nodes.values():
            if node.source != "real":
                continue
            motion = self.motion.payload(self.coordinates,self._origin)
            self._writers["data"].writerow([timestamp, node.name, self._node_id or node.id, node.source, int(node.valid),
                *node.quaternion, *node.accel, *node.gyro, *node.mag, node.temperature, node.aux_temperature,
                self._last_sequence, self._last_device_us, self._sensor_flags,
                self.latest_at, *euler_degrees(node.quaternion),
                *motion["position"], *motion["velocity"], *motion["linear_accel"], self.motion.phase, self.motion.elapsed,
                *self._raw_sample.accel, *self._raw_sample.gyro, *self._raw_sample.mag,
                int(self.motion.zupt), int(self.motion.stationary), self.motion.zupt_count])
        self.record_rows += 1
        if self.record_rows % 20 == 0:
            for handle in self._record_files.values():
                handle.flush()

    def stop_recording(self) -> None:
        for handle in self._record_files.values():
            handle.close()
        self._record_files.clear(); self._writers.clear()
        self.recording = False; self._record_started = None
