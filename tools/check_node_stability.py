"""Stationary dashboard soak test; requires the operator to keep the board still.

Uses the existing USB endpoint and preserves Wi-Fi code/configuration. Refuses
active recording/replay. Saves diagnostic polls, not a full motion recording.
"""
import argparse
import asyncio
from datetime import datetime
import json
import math
from pathlib import Path
import statistics
import time
import urllib.request
from uuid import uuid4

import websockets

BASE = "http://127.0.0.1:8000"


def read():
    with urllib.request.urlopen(BASE + "/api/body", timeout=10) as response:
        return json.load(response)


async def command(action, **fields):
    request_id = str(uuid4())
    async with websockets.connect("ws://127.0.0.1:8000/ws/body", max_size=8_000_000) as socket:
        await socket.send(json.dumps(dict(action=action, request_id=request_id, **fields)))
        async with asyncio.timeout(40):
            async for message in socket:
                result = json.loads(message).get("command_result") or {}
                if result.get("request_id") == request_id:
                    if not result.get("ok"):
                        raise RuntimeError(result.get("message"))
                    return result
    raise RuntimeError("Control connection closed before acknowledgement")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="imu_305A6077C398")
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 600:
        parser.error("seconds must be 10..600")
    initial = read()
    if initial.get("recording", {}).get("active") or initial.get("mode") != "LIVE":
        parser.error("Stop and save recording or leave replay before this test")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"started": datetime.now().isoformat(), "operator_stillness_required": True,
              "transport": "serial", "port": args.port, "wifi_implementation_changed": False,
              "full_motion_recording": False}
    polls = []

    def node():
        snapshot = read()
        item = next((d for d in snapshot["devices"] if d["device_id"] == args.device), None)
        if not item:
            raise RuntimeError("Expected physical node not present")
        return item

    try:
        asyncio.run(command("connect", endpoint_id="node-1", transport="serial", device=args.port))
        deadline = time.monotonic() + 15
        while True:
            current = node()
            if current["valid"] and current["quality"]["age_ms"] < 200:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("No fresh node data after USB connection")
            time.sleep(.25)
        report["before_calibration"] = current
        boot = current["boot_id"]
        asyncio.run(command("calibrate", device_id=args.device))
        deadline = time.monotonic() + 32
        while True:
            current = node()
            if current["boot_id"] != boot:
                raise RuntimeError("Node restarted during calibration")
            if current["stability"]["calibrated"] and not current["stability"]["calibrating"]:
                break
            if current["stability"]["phase"] in ("failed", "cancelled") or time.monotonic() > deadline:
                raise RuntimeError(current["stability"]["message"])
            time.sleep(.25)
        report["after_calibration"] = current
        started = time.monotonic()
        print("Calibration accepted; stationary soak started", flush=True)
        while time.monotonic() - started < args.seconds:
            before = time.monotonic()
            current = node()
            polls.append({"elapsed_s": time.monotonic()-started, "http_ms": (time.monotonic()-before)*1000,
                          **{key: current.get(key) for key in ("boot_id", "firmware_version", "quaternion", "euler_deg", "gyro", "accel", "mag", "residual_gyro_dps", "temperature", "valid", "quality", "stability")}})
            if not current["valid"] or current["boot_id"] != boot:
                raise RuntimeError("Node disconnected, became stale or restarted during soak")
            time.sleep(.5)
        reference = polls[0]["quaternion"]
        angles = [math.degrees(2*math.acos(min(1., abs(sum(a*b for a,b in zip(reference,p["quaternion"])))))) for p in polls]
        counters = ("valid_frames", "invalid_frames", "missing_frames", "sampling_gaps", "restarts")
        report.update(completed=True, duration_s=polls[-1]["elapsed_s"],
                      counter_deltas={key:polls[-1]["quality"][key]-polls[0]["quality"][key] for key in counters},
                      max_pose_change_deg=max(angles),
                      holding_fraction=sum(p["stability"]["holding"] for p in polls)/len(polls),
                      magnetic_fraction=sum(p["stability"]["magnetic_used"] for p in polls)/len(polls),
                      max_gyro_norm_dps=max(math.hypot(*p["gyro"]) for p in polls),
                      max_residual_gyro_dps=max(math.hypot(*p["residual_gyro_dps"]) for p in polls),
                      http_ms_max=max(p["http_ms"] for p in polls),
                      http_ms_median=statistics.median(p["http_ms"] for p in polls))
    except Exception as error:
        report.update(completed=False, error=str(error))
    finally:
        report["limitations"] = "Stationary USB service test; hold may suppress drift. Not dynamic accuracy or five-minute Wi-Fi validation."
        (args.output/"polls.json").write_text(json.dumps(polls,ensure_ascii=False,indent=2),encoding="utf-8")
        (args.output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({key:value for key,value in report.items() if key not in ("before_calibration","after_calibration")},ensure_ascii=False,indent=2),flush=True)
    return 0 if report.get("completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
