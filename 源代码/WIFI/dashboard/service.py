from __future__ import annotations

import asyncio
import csv
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import monotonic, time
from typing import Any, TextIO

from .tcp_transport import TcpTransport
from .fusion import ComplementaryFusion
from .kinematics import ShortTermBodyTracker, solve_positions
from .models import SensorSample, initial_nodes
from .protocol import CurrentCsvProtocol, FrameError
from .serial_transport import SerialTransport

DATA_HEADER = ["时间戳", "节点名称", "节点ID", "数据来源", "有效", "四元数W", "四元数X", "四元数Y", "四元数Z",
               "加速度X", "加速度Y", "加速度Z", "角速度X", "角速度Y", "角速度Z",
               "磁场X", "磁场Y", "磁场Z", "ICM温度", "LIS温度原始值"]
TRAJECTORY_HEADER = ["时间戳", "轨迹类型", "节点名称", "节点ID", "位置X米", "位置Y米", "位置Z米", "说明"]


@dataclass
class Runtime:
    port: str = "COM21"
    baudrate: int = 115200
    transport: str = "serial"
    device: str = "COM21"
    host: str = "192.168.1.120"
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

    def __post_init__(self) -> None:
        self.protocol = CurrentCsvProtocol()
        self.fusion = ComplementaryFusion()
        self.body_tracker = ShortTermBodyTracker()
        self.body_position = (0.0, 0.0, 0.0)
        self._arrival_times: deque[float] = deque()
        self._previous_arrival: float | None = None
        self._transport = None
        self._user_disconnecting = False
        self._record_started: float | None = None
        self._record_files: dict[str, TextIO] = {}
        self._writers: dict[str, csv.writer] = {}
        self.clients: set[Any] = set()

    async def connect(self, port: str | None = None, transport: str | None = None,
                      device: str | None = None, host: str | None = None,
                      tcp_port: int | None = None) -> None:
        selected_transport = transport or self.transport
        selected_device = device or port or self.port
        if selected_transport not in {"serial", "wifi"}:
            self.status, self.message = "error", f"不支持的通信方式: {selected_transport}"
            await self.broadcast()
            return
        if self._transport:
            await self.disconnect()
        self.transport, self.device = selected_transport, selected_device
        if selected_transport == "serial":
            self.port = selected_device
        else:
            self.host = (host or self.host).strip()
            self.tcp_port = int(tcp_port or self.tcp_port)
            selected_device = f"{self.host}:{self.tcp_port}"
            self.device = selected_device
            if not self._valid_endpoint(self.host, self.tcp_port):
                self.status, self.message = "error", "Wi-Fi地址或端口无效"
                await self.broadcast()
                return
        self.status, self.message = "connecting", f"正在连接 {selected_device}"
        self._user_disconnecting = False
        await self.broadcast()
        try:
            self._transport = self._new_transport()
            await self._transport.connect()
            self.status, self.message = "connected", f"已连接 {selected_device}"
        except Exception as exc:
            self._transport = None
            self.status, self.message = "error", str(exc)
            self.nodes["right_wrist"].valid = False
        await self.broadcast()

    async def disconnect(self) -> None:
        self._user_disconnecting = True
        active, self._transport = self._transport, None
        if active:
            await active.disconnect()
        self.status, self.message = "disconnected", "设备已断开"
        self.nodes["right_wrist"].valid = False
        await self.broadcast()

    def _new_transport(self):
        if self.transport == "wifi":
            return TcpTransport(self.host, self.tcp_port, self.on_transport_line, self._transport_disconnected)
        return SerialTransport(self.port, self.baudrate, self.on_transport_line, self._transport_disconnected)

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
            await self.broadcast()

    async def _transport_disconnected(self, reason: str) -> None:
        self.nodes["right_wrist"].valid = False
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
            try:
                self._transport = self._new_transport()
                await self._transport.connect()
                self.status, self.message = "connected", f"已重新连接 {self.device}"
                await self.broadcast()
                return
            except Exception as exc:
                reason = str(exc)
        self._transport = None
        self.status, self.message = "error", f"Wi-Fi重连失败: {reason}"
        await self.broadcast()

    def _update_quality(self, arrival: float) -> None:
        if self._previous_arrival is not None:
            gap = arrival - self._previous_arrival
            if gap <= 2.0:
                self.estimated_lost += max(0, round(gap * self.expected_rate) - 1)
        self._previous_arrival = arrival
        self._arrival_times.append(arrival)
        while self._arrival_times and arrival - self._arrival_times[0] > 2.0:
            self._arrival_times.popleft()

    async def consume(self, sample: SensorSample) -> None:
        node = self.nodes["right_wrist"]
        node.quaternion = self.fusion.update(sample)
        node.accel, node.gyro, node.mag = sample.accel, sample.gyro, sample.mag
        node.temperature, node.aux_temperature = sample.temperature, sample.aux_temperature
        node.updated_at, node.valid = sample.received_unix, True
        self.valid_frames += 1
        self.latest_at, self.latest_unix = sample.received_monotonic, sample.received_unix
        self._update_quality(sample.received_monotonic)
        waist = self.nodes.get("waist")
        waist_sample = sample if waist and waist.source == "real" and waist.valid else None
        self.body_position = self.body_tracker.update(waist_sample, waist.quaternion if waist_sample else None)
        positions = solve_positions(self.nodes)
        self._record(sample.received_unix, positions)
        await self.broadcast(self.payload(positions))

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

    def payload(self, positions: dict | None = None) -> dict:
        positions = positions or solve_positions(self.nodes)
        node_payloads = []
        for node in self.nodes.values():
            item = node.payload()
            item["position"] = positions[node.id]
            node_payloads.append(item)
        quality = self.quality()
        return {"version": 1, "type": "frame", "timestamp": time(), "latest_packet_at": self.latest_unix,
                "nodes": node_payloads,
                "trajectory": {"body": self.body_position, "selected_node": self.selected_record_node},
                "stats": {"serial_status": self.status, "message": self.message, "port": self.port,
                          "transport": self.transport, "device": self.device,
                          "host": self.host, "tcp_port": self.tcp_port,
                          "valid_frames": self.valid_frames, "invalid_frames": self.invalid_frames,
                          "estimated_lost": self.estimated_lost, **quality,
                          "recording": self.recording, "record_path": self.record_path,
                          "record_rows": self.record_rows,
                          "record_duration_s": round(monotonic() - self._record_started, 1) if self._record_started else 0}}

    async def broadcast(self, payload: dict | None = None) -> None:
        if not self.clients:
            return
        message = json.dumps(payload or self.payload(), ensure_ascii=False)
        stale = []
        for client in tuple(self.clients):
            try:
                await client.send_text(message)
            except Exception:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)

    async def command(self, data: dict) -> None:
        action = data.get("action")
        if action == "connect":
            await self.connect(data.get("port"), data.get("transport"), data.get("device"),
                               data.get("host"), data.get("tcp_port"))
        elif action == "disconnect":
            await self.disconnect()
        elif action == "zero":
            self.fusion.reset(); self.body_tracker.reset()
        elif action == "start_recording":
            self.selected_record_node = data.get("node_id", "right_wrist"); self.start_recording()
        elif action == "stop_recording":
            self.stop_recording()
        elif action == "select_record_node" and data.get("node_id") in self.nodes:
            self.selected_record_node = data["node_id"]
        await self.broadcast()

    def start_recording(self) -> None:
        if self.recording:
            return
        folder = Path("recordings") / f"imu-{datetime.now():%Y%m%d-%H%M%S}"
        folder.mkdir(parents=True, exist_ok=False)
        files = {"data": folder / "imu-data.csv", "body": folder / "body-trajectory.csv", "node": folder / "node-trajectory.csv"}
        for key, path in files.items():
            handle = path.open("w", encoding="utf-8-sig", newline="")
            self._record_files[key] = handle; self._writers[key] = csv.writer(handle)
        self._writers["data"].writerow(DATA_HEADER)
        self._writers["body"].writerow(TRAJECTORY_HEADER)
        self._writers["node"].writerow(TRAJECTORY_HEADER)
        self.recording, self.record_path, self.record_rows = True, str(folder), 0
        self._record_started = monotonic()

    def _record(self, timestamp: float, positions: dict[str, tuple]) -> None:
        if not self.recording:
            return
        for node in self.nodes.values():
            self._writers["data"].writerow([timestamp, node.name, node.id, node.source, int(node.valid),
                *node.quaternion, *node.accel, *node.gyro, *node.mag, node.temperature, node.aux_temperature])
        self._writers["body"].writerow([timestamp, "人体整体", "骨盆中心", "_pelvis", *self.body_position, "短时趋势估算，非绝对定位"])
        node = self.nodes[self.selected_record_node]
        self._writers["node"].writerow([timestamp, "具体节点", node.name, node.id, *positions[node.id], "骨骼约束相对位置"])
        self.record_rows += len(self.nodes) + 2
        for handle in self._record_files.values():
            handle.flush()

    def stop_recording(self) -> None:
        for handle in self._record_files.values():
            handle.close()
        self._record_files.clear(); self._writers.clear()
        self.recording = False; self._record_started = None
