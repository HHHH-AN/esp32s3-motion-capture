"""Offline, dependency-free orientation analysis of three IMU2 streams.

Angles are unsigned longitudinal-axis angles under a known neutral pose.
They are not a complete anatomical joint-coordinate-system decomposition.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
import math
from statistics import mean, pstdev

from dashboard.coordinates import CoordinateSettings
from dashboard.fusion import ComplementaryFusion, multiply, normalize
from dashboard.kinematics import rotate
from dashboard.protocol import CurrentCsvProtocol, FrameError


IDENTITY = (1.0, 0.0, 0.0, 0.0)
LIMITS = [
    "未进行加速度二次积分；骨架位置由姿态和给定骨长推算，根部固定。",
    "静态中立姿势标定依赖实际姿势、牢固佩戴和一致航向；未实现功能关节轴标定或磁力计硬铁/软铁标定。",
    "角度为无符号肢段长轴夹角；仅在规定平面动作中近似屈伸角，不是完整解剖关节角。",
    "实测时间轴使用静置段最小到达延迟估计偏移；没有硬件同步、双向授时或时钟频偏估计。匹配时间差不是真实同步误差。",
    "峰值角速度是对应传感器减去静置零偏后的角速度模长，不是关节角速度或手/球拍线速度。",
    "演示数据只验证软件流程；不能作为硬件精度、人体测量精度或训练效果证据。",
]


class ExperimentError(ValueError):
    pass


def inverse(q):
    return (q[0], -q[1], -q[2], -q[3])


def slerp(a, b, fraction):
    dot = sum(x*y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-x for x in b), -dot
    if dot > .9995:
        return normalize(tuple(x + fraction*(y-x) for x, y in zip(a, b)))
    angle = math.acos(max(-1.0, min(1.0, dot)))
    scale = math.sin(angle)
    return normalize(tuple((math.sin((1-fraction)*angle)*x + math.sin(fraction*angle)*y)/scale
                           for x, y in zip(a, b)))


def average_quaternion(quaternions):
    first = quaternions[0]
    aligned = [q if sum(a*b for a, b in zip(first, q)) >= 0 else tuple(-v for v in q)
               for q in quaternions]
    return normalize(tuple(mean(q[i] for q in aligned) for i in range(4)))


def vector_angle(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def axis_angle(a, b):
    # Compute relative rotation BEFORE extracting an angle; never subtract Euler angles.
    relative = multiply(inverse(a), b)
    return vector_angle((0, 0, 1), rotate((0, 0, 1), relative))


def rotation_angle(a, b):
    q = multiply(inverse(a), b)
    return math.degrees(2*math.acos(min(1.0, abs(q[0]))))


def add(a, b):
    return tuple(x+y for x, y in zip(a, b))


def bone(origin, q, length):
    return add(origin, rotate((0, 0, -length), q))


def frame_values(preset, rotations, speeds):
    a, b, c = rotations
    if preset["id"] == "rigid_check":
        angles = {"ab": rotation_angle(a, b), "ac": rotation_angle(a, c)}
        lines = [[(i*.25, 0, .5), add((i*.25, 0, .5), rotate((0, 0, .3), q))]
                 for i, q in enumerate(rotations)]
    elif preset["id"] == "upper_limb":
        shoulder = rotate((0, 0, .4), a)
        elbow = bone(shoulder, b, preset["lengths_m"][0])
        wrist = bone(elbow, c, preset["lengths_m"][1])
        lines = [[(0, 0, 0), shoulder], [shoulder, elbow], [elbow, wrist]]
        angles = {"elbow": axis_angle(b, c), "arm_trunk": axis_angle(a, b),
                  "trunk_tilt": axis_angle(IDENTITY, a)}
    elif preset["id"] == "lower_limb":
        hip = (0, 0, 1)
        knee = bone(hip, b, preset["lengths_m"][0])
        ankle = bone(knee, c, preset["lengths_m"][1])
        lines = [[add(hip, rotate((-.15, 0, 0), a)), add(hip, rotate((.15, 0, 0), a))],
                 [hip, knee], [knee, ankle]]
        angles = {"knee": axis_angle(b, c), "thigh_pelvis": axis_angle(a, b),
                  "pelvis_tilt": axis_angle(IDENTITY, a)}
    else:
        top = rotate((0, 0, .4), a)
        left = add(top, rotate((0, .18, 0), a))
        right = add(top, rotate((0, -.18, 0), a))
        lines = [[(0, 0, 0), top], [left, bone(left, b, preset["lengths_m"][0])],
                 [right, bone(right, c, preset["lengths_m"][1])]]
        la, ra = axis_angle(a, b), axis_angle(a, c)
        angles = {"left_raise": la, "right_raise": ra, "difference": abs(la-ra)}
    return angles, lines


def prepare_node(rows, axes, calibration_s):
    protocol = CurrentCsvProtocol()
    coordinates = CoordinateSettings.parse({"sensor_axes": axes})
    observations, last_sequence, last_device, unwrapped = [], None, None, 0.0
    lost = duplicates = invalid = 0
    actual_id = None
    for row in rows:
        try:
            sample = protocol.parse(row["line"])
        except (FrameError, UnicodeError):
            invalid += 1
            continue
        if sample is None:
            continue
        if sample.device_us is None or sample.sequence is None:
            raise ExperimentError("三节点预设要求 IMU2 时间戳与序号，不接受旧 11 列数据")
        if actual_id is not None and actual_id != sample.node_id:
            raise ExperimentError("同一 TCP 端点出现不同 node_id，请检查接线/固件或重新采集")
        actual_id = sample.node_id
        if last_sequence is not None:
            delta = (sample.sequence-last_sequence) % 2**32
            if delta == 0:
                duplicates += 1
                continue
            if delta >= 2**31:
                raise ExperimentError("设备序号倒退/重启/乱序，本轮停止；请重新采集并标定")
            lost += delta-1
        if last_device is None:
            unwrapped = sample.device_us/1e6
        else:
            dt = ((sample.device_us-last_device) % 2**32)/1e6
            if dt <= 0 or dt > .2:
                raise ExperimentError("设备采样时间倒退、重启或缺口超过 0.2 秒，本轮停止；原始数据保留")
            unwrapped += dt
        last_sequence, last_device = sample.sequence, sample.device_us
        if not sample.sensor_flags & 1:
            invalid += 1
            continue
        arrival = float(row["arrival_s"])
        if not math.isfinite(arrival) or (observations and arrival < observations[-1][1]):
            raise ExperimentError("电脑接收时间必须有限且不倒退")
        if observations and unwrapped-observations[-1][0] > .2:
            raise ExperimentError("有效六轴样本缺口超过 0.2 秒；无法恢复缺口内旋转")
        observations.append((unwrapped, arrival, coordinates.sample(sample)))
    if not observations:
        raise ExperimentError("没有有效 IMU2 六轴样本")
    start = observations[0][0]
    calibration = [item for item in observations if item[0]-start < calibration_s]
    if len(calibration) < 30 or calibration[-1][0]-start < calibration_s-.1:
        raise ExperimentError("静置标定数据不足：需至少 3 秒、30 帧")
    for _, _, sample in calibration:
        if not .85 <= math.sqrt(sum(v*v for v in sample.accel)) <= 1.15 or math.sqrt(sum(v*v for v in sample.gyro)) > 5:
            raise ExperimentError("初始静置段有明显运动：请先保持规定中立姿势至少 3 秒")
    accel_mean = tuple(mean(item[2].accel[i] for item in calibration) for i in range(3))
    accel_std = math.sqrt(mean(sum((item[2].accel[i]-accel_mean[i])**2 for i in range(3)) for item in calibration))
    if accel_std > .02:
        raise ExperimentError("初始加速度波动过大，请检查固定并重新静置")
    bias = tuple(mean(item[2].gyro[i] for item in calibration) for i in range(3))
    offset = min(arrival-device for device, arrival, _ in calibration)
    fusion = ComplementaryFusion()
    frames, neutral_quaternions = [], []
    for device, arrival, sample in observations:
        corrected = replace(sample, gyro=tuple(v-b for v, b in zip(sample.gyro, bias)),
                            received_monotonic=arrival)
        q = fusion.update(corrected)
        if calibration_s-1 <= device-start < calibration_s:
            neutral_quaternions.append(q)
        frames.append({"t": device+offset, "q": q,
                       "speed": math.sqrt(sum(v*v for v in corrected.gyro)), "device": device})
    neutral = average_quaternion(neutral_quaternions)
    usable = []
    for frame in frames:
        if frame["device"]-start >= calibration_s:
            usable.append({"t": frame["t"], "q": multiply(frame["q"], inverse(neutral)),
                           "speed": frame["speed"]})
    if len(usable) < 2:
        raise ExperimentError("静置标定之后没有足够的动作数据")
    delays = [arrival-device-offset for device, arrival, _ in observations]
    duration = observations[-1][0]-start
    return usable, {"actual_node_id": actual_id, "valid_samples": len(observations),
                    "lost_sequence_frames": lost, "duplicate_frames": duplicates, "invalid_frames": invalid,
                    "gyro_bias_dps": bias, "neutral_sensor_quaternion": neutral, "sensor_axes": axes,
                    "clock_offset_estimate_s": offset, "arrival_excess_delay_max_s": max(delays),
                    "estimated_sample_rate_hz": (len(observations)-1)/duration if duration else 0,
                    "magnetometer_valid_fraction": mean(bool(s.sensor_flags & 2) for _, _, s in observations),
                    "calibration_accel_std_g": accel_std}


def interpolate(frames, times, t, tolerance_s):
    index = bisect_left(times, t)
    if index < len(times) and abs(times[index]-t) < 1e-8:
        return frames[index]
    if index == 0 or index == len(times):
        return None
    left, right = frames[index-1], frames[index]
    span = right["t"]-left["t"]
    if span > .08 or min(t-left["t"], right["t"]-t) > tolerance_s:
        return None
    ratio = (t-left["t"])/span
    return {"q": slerp(left["q"], right["q"], ratio),
            "speed": left["speed"]+ratio*(right["speed"]-left["speed"])}


def cycles(frames, key, low, high):
    armed, active, start, peak, result = False, False, 0.0, 0.0, []
    for frame in frames:
        if not frame["valid"]:
            armed = active = False
            continue
        value = frame["angles"][key]
        if not active and value <= low:
            if not armed:
                start = frame["t"]
            armed = True
        if armed and not active and value >= high:
            active, peak = True, value
        if active:
            peak = max(peak, value)
            if value <= low:
                result.append({"start_s": start, "end_s": frame["t"], "peak_angle_deg": peak})
                armed = active = False
    return result


def analyse(preset, rows, axes, calibration_s=3.0, tolerance_s=.03):
    if len(axes) != 3:
        raise ExperimentError("必须为三个节点分别提供坐标映射")
    node_frames, metadata = [], {}
    for i, slot in enumerate(("A", "B", "C")):
        data, detail = prepare_node([row for row in rows if row["slot"] == slot], axes[i], calibration_s)
        node_frames.append(data)
        metadata[slot] = detail
    start, end = max(f[0]["t"] for f in node_frames), min(f[-1]["t"] for f in node_frames)
    if end-start < .5:
        raise ExperimentError("三个节点标定后共同覆盖的数据不足 0.5 秒")
    times = [[f["t"] for f in frames] for frames in node_frames]
    aligned = []
    for index in range(math.floor((end-start)*50)+1):
        t = start+index/50
        values = [interpolate(f, ts, t, tolerance_s) for f, ts in zip(node_frames, times)]
        if any(v is None for v in values):
            aligned.append({"t": index/50, "valid": False, "angles": {}, "speeds": [], "lines": []})
            continue
        rotations, speeds = [v["q"] for v in values], [v["speed"] for v in values]
        angles, lines = frame_values(preset, rotations, speeds)
        aligned.append({"t": index/50, "valid": True, "angles": angles,
                        "speeds": speeds, "quaternions": rotations, "lines": lines})
    valid = [frame for frame in aligned if frame["valid"]]
    if len(valid) < 25:
        raise ExperimentError("时间匹配后有效数据不足；检查端点、采样率和延迟")
    metrics = {}
    for key, label in preset["angle_labels"].items():
        values = [frame["angles"][key] for frame in valid]
        metrics[key] = {"label": label, "min_deg": min(values), "max_deg": max(values),
                        "range_deg": max(values)-min(values), "mean_deg": mean(values),
                        "std_deg": pstdev(values)}
    repetitions = {}
    for key in preset["cycle_keys"]:
        found = cycles(aligned, key, preset["cycle_low_deg"], preset["cycle_high_deg"])
        # Start/end dwell can vary. Period uses consecutive completed-return times.
        periods = [b["end_s"]-a["end_s"] for a, b in zip(found, found[1:])]
        repetitions[key] = {"count": len(found), "cycles": found, "periods_s": periods,
                            "mean_period_s": mean(periods) if periods else None,
                            "period_cv_percent": 100*pstdev(periods)/mean(periods) if len(periods) >= 2 and mean(periods) else None}
    warnings = []
    if len({m["actual_node_id"] for m in metadata.values()}) < 3:
        warnings.append("不同端点使用了重复固件 node_id；本程序按 A/B/C 连接端点区分，并保留真实 ID。扩展前建议设置独立 ID。")
    if any(m["magnetometer_valid_fraction"] < 1 for m in metadata.values()):
        warnings.append("存在磁力计无效帧：需人工对齐安装轴并先通过刚体检查，不能假定三个节点航向一致。")
    invalid_fraction = 1-len(valid)/len(aligned)
    if invalid_fraction:
        warnings.append("无法匹配的帧已留空；未跨缺口拼接动作或计数。")
    return {"preset_id": preset["id"], "title": preset["title"], "nodes": metadata,
            "duration_after_calibration_s": end-start, "display_grid_hz": 50,
            "valid_aligned_frames": len(valid), "invalid_aligned_frames": len(aligned)-len(valid),
            "alignment_tolerance_s": tolerance_s, "metrics": metrics, "repetitions": repetitions,
            # Preserve raw-rate peaks; a 50 Hz display grid can miss a short
            # 100 Hz angular-rate peak. Compare only the common time interval.
            "peak_sensor_gyro_dps": {slot: max(f["speed"] for f in node_frames[i] if start <= f["t"] <= end)
                                     for i, slot in enumerate(("A", "B", "C"))},
            "warnings": warnings, "limitations": LIMITS, "frames": aligned}
