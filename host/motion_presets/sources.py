"""Synthetic IMU2 generation and explicit three-endpoint TCP capture."""
from __future__ import annotations

import asyncio
import csv
import math
from time import monotonic

from dashboard.fusion import euler_quaternion, multiply
from dashboard.kinematics import rotate
from dashboard.protocol import CurrentCsvProtocol, FrameError
from .engine import ExperimentError, IDENTITY, inverse


RAW_FIELDS = ["slot", "arrival_s", "line"]


def pose(preset_id, slot, t):
    # All simulated nodes are static for the first 4 seconds. No translation,
    # noise, magnetic distortion or soft-tissue movement is simulated.
    u = max(0, t-4)
    rise = .5*(1-math.cos(2*math.pi*u/4))
    if preset_id == "rigid_check":
        return euler_quaternion(.35*math.sin(u), .3*math.sin(.7*u), .5*math.sin(.4*u))
    if preset_id == "upper_limb":
        tilt = math.radians(4)*rise
        angle = tilt if slot == "A" else tilt + math.radians(25)*rise
        if slot == "C":
            angle += math.radians(90)*rise
        return euler_quaternion(0, angle, 0)
    if preset_id == "lower_limb":
        angle = math.radians(5)*rise if slot == "A" else math.radians(-35)*rise
        if slot == "C":
            angle += math.radians(80)*rise
        return euler_quaternion(0, angle, 0)
    angle = 0 if slot == "A" else math.radians(80 if slot == "B" else -65)*rise
    return euler_quaternion(angle, 0, 0)


def raw_vector(mapped, axes):
    raw = [0.0, 0.0, 0.0]
    for axis, value in zip(axes, mapped):
        raw["XYZ".index(axis[1])] = value*(1 if axis[0] == "+" else -1)
    return raw


def demo_rows(preset, duration_s, axes, rate=100):
    mounts = [euler_quaternion(.18, -.12, .25), euler_quaternion(-.25, .2, -.4),
              euler_quaternion(.32, .14, .55)]
    starts = [10_000_000, 80_000_000, 2**32-1_500_000]
    previous = dict.fromkeys(("A", "B", "C"), IDENTITY)
    for index in range(round(duration_s*rate)+1):
        t = index/rate
        for number, slot in enumerate(("A", "B", "C")):
            q = multiply(pose(preset["id"], slot, t), mounts[number])
            delta = multiply(inverse(previous[slot]), q)
            if delta[0] < 0:
                delta = tuple(-v for v in delta)
            sine = math.sqrt(sum(v*v for v in delta[1:]))
            angle = 2*math.atan2(sine, delta[0])
            gyro = tuple(math.degrees(v*angle/sine*rate) if sine > 1e-12 and index else 0.0 for v in delta[1:])
            accel = rotate((0, 0, 1), inverse(q))
            mag = rotate((30, 0, 10), inverse(q))
            values = [*raw_vector(accel, axes[number]), *raw_vector(gyro, axes[number]),
                      25, *raw_vector(mag, axes[number]), 0]
            line = f"IMU2,demo_{slot},{index},{(starts[number]+round(t*1e6)) % 2**32},3," + ",".join(f"{v:.8f}" for v in values)
            previous[slot] = q
            yield {"slot": slot, "arrival_s": t, "line": line}


async def capture_tcp(endpoints, duration_s, writer, on_progress=print):
    """Connect only to the three explicitly configured hosts. No discovery/scan."""
    opened = []
    rows = []
    protocol = CurrentCsvProtocol()
    try:
        connections = await asyncio.gather(*(asyncio.wait_for(asyncio.open_connection(host, port), 5)
                                             for host, port in endpoints), return_exceptions=True)
        opened = [value for value in connections if not isinstance(value, BaseException)]
        errors = [str(value) for value in connections if isinstance(value, BaseException)]
        if errors:
            raise ExperimentError("三节点连接未全部成功：" + "; ".join(errors))
        origin = monotonic()

        async def receive(slot, reader):
            count = 0
            while True:
                remaining = duration_s-(monotonic()-origin)
                if remaining <= 0:
                    return count
                try:
                    raw = await asyncio.wait_for(reader.readline(), min(3, remaining))
                except asyncio.TimeoutError:
                    if monotonic()-origin >= duration_s-.02:
                        return count
                    raise ExperimentError(f"节点 {slot} 超过 3 秒无数据，本轮停止")
                if not raw:
                    raise ExperimentError(f"节点 {slot} TCP 已断开，本轮停止")
                if len(raw) > 4096 or not raw.endswith(b"\n"):
                    raise ExperimentError(f"节点 {slot} 帧过长或不完整")
                try:
                    line = raw.decode("utf-8").strip()
                except UnicodeError as exc:
                    raise ExperimentError(f"节点 {slot} 数据不是 UTF-8") from exc
                row = {"slot": slot, "arrival_s": monotonic()-origin, "line": line}
                writer.writerow(row)
                rows.append(row)
                try:
                    sample = protocol.parse(line)
                except FrameError:
                    continue
                if sample is not None:
                    count += 1

        tasks = [asyncio.create_task(receive(slot, connection[0]))
                 for slot, connection in zip(("A", "B", "C"), connections)]
        try:
            on_progress("三个端点已连接。请保持预设中立姿势至少 4 秒，再开始慢速动作。")
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return rows
    finally:
        for _, stream in opened:
            stream.close()
        if opened:
            await asyncio.gather(*(asyncio.wait_for(stream.wait_closed(), 1) for _, stream in opened),
                                 return_exceptions=True)


def read_raw(path):
    with open(path, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != RAW_FIELDS:
            raise ExperimentError("回放输入需为本程序的 raw.csv（slot,arrival_s,line）")
        rows = list(reader)
    if any(row["slot"] not in ("A", "B", "C") for row in rows):
        raise ExperimentError("原始记录中出现未知 A/B/C 槽位")
    return rows
