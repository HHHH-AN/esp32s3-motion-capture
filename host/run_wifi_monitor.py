"""Live, rotation-only Wi-Fi monitor for one to three real IMU2 TCP endpoints.

Only Python's standard library is required. The web server binds to loopback.
Example: python run_wifi_monitor.py --node A=192.168.4.1:9000
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import replace
import json
from pathlib import Path
import socket
import threading
from time import monotonic
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dashboard.coordinates import CoordinateSettings
from dashboard.attitude_stability import AttitudeStabilizer
from dashboard.fusion import ComplementaryFusion, euler_degrees, relative
from dashboard.protocol import CurrentCsvProtocol, FrameError
from dashboard.tcp_transport import LineReassembler


ROOT = Path(__file__).resolve().parent


class WifiNode:
    def __init__(self, slot, host, port, coordinates):
        self.slot, self.host, self.port = slot, host, port
        self.coordinates = coordinates
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.fusion, self.protocol = ComplementaryFusion(gravity_vector_correction=True), CurrentCsvProtocol()
        self.stability = AttitudeStabilizer()
        self.calibration_node_id = None
        self.previous_connection = None
        self.stability_enabled = True
        self.reference = None
        self.quaternion = (1., 0., 0., 0.)
        self.node_id = None
        self.last_sequence = self.last_device_us = None
        self.latest = None
        self.flags = self.frames = self.invalid = self.missing = self.duplicates = self.restarts = 0
        self.sampling_gaps = 0
        self.last_gap_s = 0.
        self.accel, self.gyro, self.mag = (0.,)*3, (0.,)*3, (0.,)*3
        self.arrivals = deque(maxlen=500)
        self.status = "等待连接"
        self.connected = False
        self.thread = None

    def reset_attitude(self):
        self.fusion.reset()
        self.reference = None
        self.last_sequence = self.last_device_us = None
        self.stability.reset_window("连接中断或采样重启")

    def consume(self, raw, arrival=None):
        now = monotonic() if arrival is None else arrival
        try:
            sample = self.protocol.parse(raw.decode("utf-8"))
        except (UnicodeError, FrameError):
            with self.lock:
                self.invalid += 1
            return
        if sample is None:
            return
        with self.lock:
            if sample.sequence is None or sample.device_us is None or not sample.sensor_flags & 1:
                self.invalid += 1
                return
            if self.node_id is not None and sample.node_id != self.node_id:
                self.invalid += 1
                self.status = "同一端点节点 ID 改变，请重新连接"
                return
            if self.previous_connection is not None:
                old_id, old_sequence, old_us = self.previous_connection
                if (sample.node_id != old_id or
                        (sample.sequence-old_sequence) % 2**32 >= 2**31 or
                        (sample.device_us-old_us) % 2**32 >= 2**31):
                    self.stability.clear()
                    self.stability.message = "设备更换或重启：请重新静置校准"
                self.previous_connection = None
            if self.last_sequence is not None:
                delta = (sample.sequence-self.last_sequence) % 2**32
                if delta == 0:
                    self.duplicates += 1
                    return
                dt = ((sample.device_us-self.last_device_us) % 2**32)/1e6
                if delta >= 2**31 or dt == 0 or dt >= 2**31/1e6:
                    self.restarts += 1
                    self.stability.clear()
                    self.stability.message = "设备重启：请重新静置校准"
                    self.reset_attitude()
                else:
                    self.missing += delta-1
                    if dt > .2:
                        # No measurements describe motion inside this gap.
                        # Keep q/reference and skip integration across it;
                        # resetting the reference would visibly jump to zero.
                        self.sampling_gaps += 1
                        self.last_gap_s = dt
                        self.stability.reset_window("采样中断，请重新静置校准")
                        self.fusion.last_time = now
                        self.fusion.last_device_us = sample.device_us
            self.node_id = sample.node_id
            if self.calibration_node_id != sample.node_id:
                self.stability.clear()
                self.calibration_node_id = sample.node_id
            self.last_sequence, self.last_device_us = sample.sequence, sample.device_us
            sample.received_monotonic = now
            mapped = self.coordinates.sample(sample)
            just_calibrated = self.stability.update(mapped)
            if just_calibrated:
                self.fusion.reset()
                self.reference = None
            corrected = self.stability.guard_magnetometer(self.stability.corrected(mapped))
            holding = self.stability_enabled and self.stability.stationary
            # Keep the fusion clock current while holding; no delayed catch-up
            # integration or magnetic correction may rotate a confirmed rest.
            fusion_sample = replace(corrected, gyro=(0., 0., 0.)) if holding else corrected
            q = self.fusion.update(fusion_sample, correction_scale=0. if holding else 1.)
            if self.reference is None:
                self.reference = q
            self.quaternion = relative(q, self.reference)
            self.accel, self.gyro, self.mag = mapped.accel, mapped.gyro, mapped.mag
            self.flags, self.latest = sample.sensor_flags, now
            self.frames += 1
            self.arrivals.append(now)
            self.status = "Wi-Fi 实时接收"

    def calibrate(self):
        with self.lock:
            if not self.connected or self.latest is None or monotonic()-self.latest > 1.5:
                return False
            self.stability.start_calibration(now=monotonic())
            return True

    def set_stability(self, enabled):
        with self.lock:
            self.stability_enabled = enabled

    def zero(self):
        with self.lock:
            if not self.connected or self.latest is None or monotonic()-self.latest > 1.5:
                return False
            self.reference = self.fusion.q
            self.quaternion = (1., 0., 0., 0.)
            return True

    def snapshot(self):
        with self.lock:
            self.stability.expire(monotonic())
            age = monotonic()-self.latest if self.latest is not None else None
            recent = [t for t in self.arrivals if monotonic()-t <= 2]
            hz = (len(recent)-1)/(recent[-1]-recent[0]) if len(recent) >= 2 and recent[-1] > recent[0] else 0
            stability = {"calibrated": self.stability.calibrated,
                         "calibrating": self.stability.calibrating and self.connected and age is not None and age <= 1.5,
                         "message": self.stability.message, "progress": self.stability.progress,
                         "quality": self.stability.calibration_quality,
                         "phase": self.stability.phase, "retries": self.stability.retries,
                         "gyro_bias_dps": self.stability.bias,
                         "corrected_gyro_dps": tuple(v-b for v, b in zip(self.gyro, self.stability.bias)),
                         "enabled": self.stability_enabled,
                         "magnetic_used": self.stability.magnetic_used,
                         "magnetic_message": self.stability.magnetic_message,
                         "holding": self.stability_enabled and self.stability.stationary and self.connected and age is not None and age <= 1.5}
            return {"slot": self.slot, "endpoint": f"{self.host}:{self.port}", "configured": True,
                    "node_id": self.node_id, "connected": self.connected,
                    "valid": self.connected and age is not None and age <= 1.5,
                    "status": self.status, "age_s": age, "rate_hz": hz,
                    "quaternion": self.quaternion, "euler_deg": euler_degrees(self.quaternion),
                    "accel": self.accel, "gyro": self.gyro, "mag": self.mag, "sensor_flags": self.flags,
                    "frames": self.frames, "sequence": self.last_sequence, "missing_frames": self.missing,
                    "invalid_frames": self.invalid, "duplicate_frames": self.duplicates,
                    "device_us": self.last_device_us, "sampling_gaps": self.sampling_gaps,
                    "last_gap_s": self.last_gap_s,
                    "attitude_reinitializations": self.restarts, "stability": stability}

    def start(self):
        self.thread = threading.Thread(target=self._receive, name=f"IMU-{self.slot}", daemon=True)
        self.thread.start()

    def _receive(self):
        while not self.stop.is_set():
            try:
                with socket.create_connection((self.host, self.port), timeout=2) as connection:
                    connection.settimeout(3)
                    reassembler = LineReassembler()
                    with self.lock:
                        self.connected = True
                        if self.node_id is not None and self.last_sequence is not None:
                            self.previous_connection = (self.node_id, self.last_sequence, self.last_device_us)
                        self.node_id = None
                        self.reset_attitude()
                        self.status = "TCP 已连接，等待真实数据"
                    while not self.stop.is_set():
                        chunk = connection.recv(4096)
                        if not chunk:
                            raise ConnectionError("ESP32 已关闭 TCP")
                        lines, discarded = reassembler.feed(chunk)
                        with self.lock:
                            self.invalid += discarded
                        for line in lines:
                            self.consume(line)
            except (OSError, ValueError) as exc:
                with self.lock:
                    self.status = f"未连接，2 秒后重试：{exc}"
            finally:
                with self.lock:
                    self.connected = False
                    self.stability.reset_window("Wi-Fi 断开，请重连后重试")
            self.stop.wait(2)


def handler_for(nodes):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, payload, content_type="application/json; charset=utf-8"):
            data = payload.encode("utf-8") if isinstance(payload, str) else payload
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.send(200, (ROOT/"web"/"wifi_monitor.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/pose_math.js":
                self.send(200, (ROOT/"web"/"pose_math.js").read_bytes(), "application/javascript; charset=utf-8")
            elif self.path == "/api/status":
                states = {slot: node.snapshot() for slot, node in nodes.items()}
                self.send(200, json.dumps({"source": "real_wifi_tcp", "nodes": states,
                                          "position_integration": False}, ensure_ascii=False, allow_nan=False))
            else:
                self.send(404, '{"error":"not found"}')

        def do_POST(self):
            if self.path not in ("/api/zero", "/api/calibrate", "/api/stability"):
                return self.send(404, '{"error":"not found"}')
            origin = self.headers.get("Origin")
            if origin and origin != "http://"+self.headers.get("Host", ""):
                return self.send(403, '{"error":"origin rejected"}')
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 256:
                    raise ValueError("invalid request size")
                command = json.loads(self.rfile.read(size))
                slot = command.get("slot")
                if slot not in nodes:
                    return self.send(409, '{"error":"node not online"}')
                if self.path == "/api/stability":
                    if type(command.get("enabled")) is not bool:
                        raise ValueError("enabled must be boolean")
                    nodes[slot].set_stability(command["enabled"])
                else:
                    action = nodes[slot].zero if self.path == "/api/zero" else nodes[slot].calibrate
                    if not action():
                        return self.send(409, '{"error":"node not online"}')
                self.send(200, '{"ok":true}')
            except (ValueError, AttributeError):
                self.send(400, '{"error":"invalid request"}')

        def log_message(self, *_):
            pass
    return Handler


def parse_nodes(values):
    result = {}
    for value in values:
        try:
            slot, endpoint = value.split("=", 1)
            host, port_text = endpoint.rsplit(":", 1)
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("格式为 --node A=192.168.4.1:9000") from exc
        if slot not in "ABC" or len(slot) != 1 or slot in result or not host or any(c.isspace() for c in host) or not 1 <= port <= 65535:
            raise ValueError("节点槽位需为不重复的 A/B/C，端点格式和端口需有效")
        if (host, port) in result.values():
            raise ValueError("不能把同一 TCP 端点配置成多个节点")
        result[slot] = (host, port)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", action="append", required=True, help="A=host:port; repeat for B and C")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    try:
        endpoints = parse_nodes(args.node)
        if not 1 <= args.port <= 65535:
            raise ValueError("Web port must be 1..65535")
    except ValueError as exc:
        parser.error(str(exc))
    coordinates = CoordinateSettings.parse(json.loads((ROOT/"coordinate_settings.json").read_text(encoding="utf-8")))
    nodes = {slot: WifiNode(slot, host, port, coordinates) for slot, (host, port) in endpoints.items()}
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(nodes))
    for node in nodes.values():
        node.start()
    print(f"Rotation-only monitor: http://127.0.0.1:{args.port}/", flush=True)
    print("Real TCP nodes only. Join the configured Wi-Fi; disconnected nodes are shown offline.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for node in nodes.values():
            node.stop.set()
        server.server_close()
        for node in nodes.values():
            node.thread.join(timeout=5)


if __name__ == "__main__":
    main()
