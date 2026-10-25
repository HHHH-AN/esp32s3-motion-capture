"""Temporarily join a saved Wi-Fi profile, validate IMU2 TCP, restore Wi-Fi.

No passwords are read. No USB serial connection is opened. A detached recovery
process restores the previous saved profile if this process terminates early.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "host"
sys.path.insert(0, str(HOST))
from dashboard.coordinates import CoordinateSettings
from dashboard.fusion import ComplementaryFusion, euler_degrees, relative
from dashboard.protocol import CurrentCsvProtocol, FrameError
from dashboard.tcp_transport import LineReassembler
from run_wifi_monitor import parse_nodes


def netsh(*args):
    result = subprocess.run(["netsh", "wlan", *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=12)
    return result.stdout.decode("utf-8", "replace")


def state():
    text = netsh("show", "interfaces")
    def field(name):
        found = re.search(r"^\s*"+name+r"\s*:\s*(.*?)\s*$", text, re.M)
        return found.group(1) if found else None
    return {"state": field("State"), "ssid": field("SSID"), "profile": field("Profile")}


def connect(profile, interface):
    return netsh("connect", "name="+profile, "interface="+interface)


def wait_profile(profile, seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        current = state()
        if current["profile"] == profile and current["state"] == "connected":
            return current
        time.sleep(.7)
    raise ConnectionError(f"Windows 未在 {seconds} 秒内完成关联：{profile}; state={state()}")


def capture(host, port, seconds, folder):
    protocol, fusion, reassembler = CurrentCsvProtocol(), ComplementaryFusion(), LineReassembler()
    settings = CoordinateSettings.parse(json.loads((HOST/"coordinate_settings.json").read_text(encoding="utf-8")))
    packets, invalid, lost, last_sequence, node_id, reference = [], 0, 0, None, None, None
    # WLAN association can complete before DHCP installs the IPv4 route.
    connection = None
    deadline = time.monotonic()+12
    last_error = None
    while connection is None and time.monotonic() < deadline:
        try:
            connection = socket.create_connection((host, port), timeout=2)
        except OSError as exc:
            last_error = exc
            time.sleep(.8)
    if connection is None:
        raise ConnectionError(f"TCP route/connection not ready after 12 seconds: {last_error}")
    with connection:
        connection.settimeout(2)
        local_address = connection.getsockname()[0]
        started = time.monotonic()
        with (folder/"wifi_raw.csv").open("w", encoding="utf-8-sig", newline="") as raw:
            writer = csv.writer(raw)
            writer.writerow(["arrival_monotonic_s", "imu2_line"])
            while time.monotonic()-started < seconds:
                chunk = connection.recv(4096)
                if not chunk:
                    raise ConnectionError("ESP32 TCP connection closed")
                arrival = time.monotonic()
                lines, discarded = reassembler.feed(chunk, arrival)
                invalid += discarded
                for data in lines:
                    try:
                        line = data.decode("utf-8")
                        sample = protocol.parse(line)
                    except (UnicodeError, FrameError):
                        invalid += 1
                        continue
                    if sample is None:
                        continue
                    writer.writerow([arrival, line])
                    if sample.sequence is None or sample.device_us is None or not sample.sensor_flags & 1:
                        raise ValueError("Expected valid IMU2 six-axis sample")
                    if node_id is not None and sample.node_id != node_id:
                        raise ValueError("Node ID changed within the same TCP connection")
                    node_id = sample.node_id
                    if last_sequence is not None:
                        delta = (sample.sequence-last_sequence) % 2**32
                        if not 0 < delta < 2**31:
                            raise ValueError("Duplicate, restart or out-of-order sequence")
                        lost += delta-1
                    last_sequence = sample.sequence
                    sample.received_monotonic = arrival
                    q = fusion.update(settings.sample(sample))
                    if reference is None:
                        reference = q
                    q_relative = relative(q, reference)
                    packets.append({"time_s": arrival-started, "sequence": sample.sequence,
                                    "device_us": sample.device_us, "sensor_flags": sample.sensor_flags,
                                    "quaternion": q_relative, "euler_deg": euler_degrees(q_relative),
                                    "accel_norm_g": sum(v*v for v in sample.accel)**.5,
                                    "gyro_norm_dps": sum(v*v for v in sample.gyro)**.5})
    if len(packets) < 2:
        raise ValueError("Not enough packets received")
    elapsed = packets[-1]["time_s"]-packets[0]["time_s"]
    device_elapsed = ((packets[-1]["device_us"]-packets[0]["device_us"]) % 2**32)/1e6
    (folder/"orientation_frames.json").write_text(json.dumps(packets, ensure_ascii=False), encoding="utf-8")
    return {"wifi_transport_passed": len(packets) >= 500 and invalid == 0,
            "frames": len(packets), "node_id": node_id, "invalid_frames": invalid,
            "sequence_missing_frames": lost, "capture_duration_s": elapsed,
            "received_hz": (len(packets)-1)/elapsed, "device_hz": (len(packets)-1)/device_elapsed,
            "six_axis_valid_frames": sum(bool(p["sensor_flags"] & 1) for p in packets),
            "magnetometer_valid_frames": sum(bool(p["sensor_flags"] & 2) for p in packets),
            "local_wifi_ipv4": local_address, "remote_tcp": f"{host}:{port}",
            "accel_norm_g_range": [min(p["accel_norm_g"] for p in packets), max(p["accel_norm_g"] for p in packets)],
            "max_gyro_norm_dps": max(p["gyro_norm_dps"] for p in packets),
            "usb_serial_opened_by_test": False,
            "limitations": "USB cable remains attached for power. Rotation accuracy, battery unplugging and three-node operation were not verified."}


def check_monitor(url, host, port, seconds, folder, monitor_nodes=None):
    endpoints = monitor_nodes or {"A": (host, port)}
    deadline = time.monotonic()+15
    polls = []
    first = None
    last = None
    counter_fields = ("frames", "invalid_frames", "missing_frames", "attitude_reinitializations",
                      "duplicate_frames")
    try:
        while time.monotonic() < deadline:
            with urlopen(url.rstrip("/")+"/api/status", timeout=2) as response:
                payload = json.load(response)
            # Keep every complete response, including warm-up/failure states,
            # so simultaneous reception can be audited instead of inferred
            # from separate requests for each node.
            polls.append(payload)
            if payload.get("source") != "real_wifi_tcp":
                raise ValueError("Monitor source does not match the real ESP32 test")
            states = payload.get("nodes", {})
            for slot, (node_host, node_port) in endpoints.items():
                node = states.get(slot, {})
                if node.get("endpoint") != f"{node_host}:{node_port}":
                    raise ValueError(f"Monitor endpoint for {slot} does not match the configured ESP32")
            if all(states[slot].get("valid") for slot in endpoints):
                node_ids = [states[slot].get("node_id") for slot in endpoints]
                if any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
                    raise ValueError("Every live monitor node must have a nonempty node ID")
                if len(set(node_ids)) != len(node_ids):
                    raise ValueError("Configured monitor nodes must have independent node IDs")
                for slot in endpoints:
                    node = states[slot]
                    if type(node.get("sensor_flags")) is not int or not node["sensor_flags"] & 1:
                        raise ValueError(f"Monitor node {slot} does not have a valid six-axis sensor")
                    for field in counter_fields:
                        if type(node.get(field)) is not int or node[field] < 0:
                            raise ValueError(f"Monitor node {slot} has an invalid {field} counter")
                    if first is not None:
                        if node["node_id"] != first[slot]["node_id"]:
                            raise ValueError(f"Monitor node {slot} changed identity during validation")
                        for field in counter_fields:
                            if node[field] < last[slot][field]:
                                raise ValueError(f"Monitor node {slot} reset its {field} counter")
                        for field in ("invalid_frames", "missing_frames", "attitude_reinitializations"):
                            if node[field] != first[slot][field]:
                                raise ValueError(f"Monitor node {slot} added {field} during validation")
                if first is None:
                    first = {slot: states[slot] for slot in endpoints}
                    deadline = time.monotonic()+seconds
                last = {slot: states[slot] for slot in endpoints}
            elif first is not None:
                raise ConnectionError("Live monitor lost one or more simultaneous Wi-Fi nodes during validation")
            time.sleep(.1)
    finally:
        (folder/"monitor_polls.json").write_text(json.dumps(polls, ensure_ascii=False, indent=2), encoding="utf-8")
    if first is None or len(polls) < 2:
        raise ConnectionError("Live monitor did not receive all configured Wi-Fi nodes together within 15 seconds")
    node_reports = {}
    for slot in endpoints:
        before, after = first[slot], last[slot]
        deltas = {field: after[field]-before[field] for field in counter_fields}
        node_reports[slot] = {
            "wifi_transport_passed": deltas["frames"] >= 500,
            "endpoint": after["endpoint"], "node_id": after["node_id"],
            "frames_received_during_monitor_check": deltas["frames"],
            "counter_deltas": deltas, "received_hz_last": after["rate_hz"],
            "sampling_gaps_during_check": after.get("sampling_gaps", 0)-before.get("sampling_gaps", 0),
            "sensor_flags": after["sensor_flags"],
            "first_monitor_state": before, "last_monitor_state": after}
    report = {"wifi_transport_passed": all(node["wifi_transport_passed"] for node in node_reports.values()),
            "validation_path": "ESP32 Wi-Fi TCP -> independent fusion -> simultaneous local HTTP API",
            "monitor_url": url, "simultaneous_nodes_validated": list(endpoints),
            "nodes": node_reports,
            "frames_received_during_monitor_check": sum(node["frames_received_during_monitor_check"] for node in node_reports.values()),
            "monitor_payload_poll_count": len(polls), "monitor_polls_file": str(folder/"monitor_polls.json"),
            "usb_serial_opened_by_test": False,
            "limitations": "Physical rotation accuracy, battery unplugging and hardware sampling synchronization were not verified."}
    # Preserve the single-A report fields used by previous validation records.
    if len(node_reports) == 1:
        only = next(iter(node_reports.values()))
        report.update({key: only[key] for key in ("node_id", "received_hz_last", "sensor_flags",
                                                 "first_monitor_state", "last_monitor_state")})
        report.update(missing_frames=only["last_monitor_state"]["missing_frames"],
                      invalid_frames=only["last_monitor_state"]["invalid_frames"])
    return report


def calibrate_monitor(url, endpoints, folder):
    """Only call after the user explicitly confirms every board is stationary."""
    polls = []
    def read():
        with urlopen(url.rstrip("/")+"/api/status", timeout=2) as response:
            payload = json.load(response)
        polls.append(payload)
        if payload.get("source") != "real_wifi_tcp" or any(
                payload.get("nodes", {}).get(slot, {}).get("endpoint") != f"{host}:{port}"
                for slot, (host, port) in endpoints.items()):
            raise ValueError("Calibration monitor source/endpoints do not match the requested real nodes")
        return payload["nodes"]
    try:
        deadline = time.monotonic()+12
        while True:
            states = read()
            if all(states.get(slot, {}).get("valid") for slot in endpoints):
                break
            if time.monotonic() > deadline:
                raise ConnectionError("Both nodes must be online before stationary calibration")
            time.sleep(.1)
        # A bounded retry keeps the same acceptance thresholds; it never turns
        # a rejected window into a pass. Keep all boards still throughout.
        for attempt in range(3):
            for slot in endpoints:
                request = Request(url.rstrip("/")+"/api/calibrate", data=json.dumps({"slot": slot}).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=2) as response:
                    if not json.load(response).get("ok"):
                        raise ValueError("Stationary calibration request failed")
            deadline = time.monotonic()+11
            while True:
                states = read()
                if not all(states[slot].get("valid") for slot in endpoints):
                    raise ConnectionError("Disconnected while calibrating")
                if all(not states[slot]["stability"]["calibrating"] for slot in endpoints):
                    if all(states[slot]["stability"]["calibrated"] and
                           states[slot]["stability"]["progress"] == 1 for slot in endpoints):
                        return {slot: states[slot]["stability"] for slot in endpoints}
                    break
                if time.monotonic() > deadline:
                    raise ConnectionError("Stationary calibration timed out")
                time.sleep(.1)
        raise ValueError("Calibration rejected after 3 attempts: "+str({s: states[s]["stability"] for s in endpoints}))
    finally:
        (folder/"calibration_polls.json").write_text(json.dumps(polls, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="ESP32-IMU")
    parser.add_argument("--interface", default="WLAN")
    parser.add_argument("--host", default="192.168.4.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--seconds", type=float, default=12)
    parser.add_argument("--restore-only")
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--monitor-url", help="Validate the running local monitor instead of opening a second TCP client")
    parser.add_argument("--monitor-node", action="append", help="Expected monitor endpoint, e.g. A=192.168.4.1:9000; repeat for B/C (default: A=host:port)")
    parser.add_argument("--calibrate", action="store_true", help="Explicitly request 4 s stationary calibration first; user must keep all configured boards still")
    parser.add_argument("--start-delay", type=float, default=0, help="Optional 0..30 s delay before a UI-coordinated test")
    args = parser.parse_args()
    if args.restore_only:
        time.sleep(args.delay)
        connect(args.restore_only, args.interface)
        return 0
    if not 6 <= args.seconds <= 20 or not 1 <= args.port <= 65535:
        parser.error("seconds must be 6..20, port 1..65535")
    if not 0 <= args.start_delay <= 30:
        parser.error("start-delay must be 0..30 seconds")
    if args.monitor_url:
        url = urlparse(args.monitor_url)
        if url.scheme != "http" or url.hostname != "127.0.0.1" or url.path not in ("", "/") or url.query:
            parser.error("monitor-url must be an http://127.0.0.1:PORT/ local monitor")
    if (args.monitor_node or args.calibrate) and not args.monitor_url:
        parser.error("monitor-node/calibrate requires monitor-url")
    try:
        monitor_nodes = parse_nodes(args.monitor_node) if args.monitor_node else {"A": (args.host, args.port)}
    except ValueError as exc:
        parser.error(str(exc))
    time.sleep(args.start_delay)
    original = state()
    restore_profile = original["profile"]
    if not restore_profile:
        parser.error("Cannot identify the saved Wi-Fi profile to restore")
    folder = HOST/"hardware_tests"/f"wifi-{datetime.now():%Y%m%d-%H%M%S-%f}"
    folder.mkdir(parents=True, exist_ok=False)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    recovery = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--restore-only", restore_profile,
                                 "--interface", args.interface, "--delay", "100" if args.calibrate else "65"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    report = {"before": original, "test_profile": args.profile, "output": str(folder)}
    try:
        report["connect_request"] = connect(args.profile, args.interface)
        report["associated"] = wait_profile(args.profile, 20)
        # Allow DHCP to settle before the bounded TCP connection attempt.
        time.sleep(2)
        if args.monitor_url:
            if args.calibrate:
                report["stationary_calibration"] = calibrate_monitor(args.monitor_url, monitor_nodes, folder)
            report.update(check_monitor(args.monitor_url, args.host, args.port, args.seconds, folder, monitor_nodes))
        else:
            report.update(capture(args.host, args.port, args.seconds, folder))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.update(wifi_transport_passed=False, error=str(exc))
    finally:
        try:
            ip = subprocess.run(["netsh", "interface", "ipv4", "show", "config", "name="+args.interface],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
            report["tested_wifi_ipv4_config"] = ip.stdout.decode("utf-8", "replace")
        except subprocess.SubprocessError:
            pass
        try:
            connect(restore_profile, args.interface)
            report["after"] = wait_profile(restore_profile, 15)
            report["original_wifi_restored"] = True
            recovery.terminate()
            recovery.wait(timeout=3)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            report["original_wifi_restored"] = False
            report["restore_error"] = str(exc)
        (folder/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("wifi_transport_passed") and report.get("original_wifi_restored") else 1


if __name__ == "__main__":
    raise SystemExit(main())
