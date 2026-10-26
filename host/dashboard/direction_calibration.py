"""Functional sensor installation calibration from gravity and a signed hinge.

All rotations are active, right-handed WXYZ.  Sensor axes have already passed
the device CoordinateSettings map.  Let C map neutral sensor coordinates into
the neutral body/bone frame and F be the device's arbitrary *fixed* fusion frame:

    Q(t) = F R_body(t) C,   Q0 = F C
    D(t) = inverse(Q0) Q(t) = inverse(C) R_body(t) C

Gravity at neutral supplies C^-1 Z.  A wearer-declared forward arm raise from
the hanging -Z segment supplies the signed hinge C^-1(-Y).  Two nonparallel
vectors identify a proper rotation C; a neutral pose alone cannot.  The actual
world alignment is A=C inverse(Q0), installation M=inverse(C), and R=A Q M.

The anatomical word 'forward' is an external instruction, not something two
IMUs can independently verify.  The fit rejects contradictory geometry and bad
data but cannot prove the wearer faced/moved in the declared direction.  Use
unfitted side raise and elbow flexion for the separate validation step.  This
calibration never estimates gyro bias or repairs time-varying heading drift.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from statistics import median

from .body_math import IDENTITY, angle_degrees, inverse, mean, multiply, quaternion, rotate


SCHEMA_VERSION = "functional-installation/1"
ALGORITHM_VERSION = "gravity-directed-hinge/1"
SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config/direction_v1.json"
IDENTITY_FIELDS = ("device_id", "body_slot", "boot_id", "processing_profile", "fusion_version", "reference_epoch", "reference_revision", "sensor_axes")


class CalibrationError(ValueError):
    def __init__(self, code, message, quality=None):
        super().__init__(message)
        self.code = code
        self.quality = quality or {}


def load_settings(config=None):
    defaults = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    if config:
        defaults.update(config)
    if defaults.get("schema_version") != "functional-direction-settings/1":
        raise CalibrationError("settings_version", "方向标定配置版本不支持")
    for key, value in defaults.items():
        if key not in ("schema_version", "forward_raise_axis_body", "neutral_up_body"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise CalibrationError("settings_invalid", "方向标定阈值必须为有限正数："+key)
    # These labels fix the current body convention rather than add unobserved
    # model degrees of freedom. A new convention requires a new format version.
    if defaults["forward_raise_axis_body"] != [0., -1., 0.] or defaults["neutral_up_body"] != [0., 0., 1.]:
        raise CalibrationError("settings_coordinates", "本版本要求 X前/Y左/Z上、前举轴 -Y")
    if not 0 < defaults["static_outlier_fraction"] <= .1:
        raise CalibrationError("settings_invalid", "定姿异常值比例须大于0且不超过10%")
    if defaults["static_wait_timeout_seconds"] <= defaults["static_prepare_seconds"]+defaults["static_capture_seconds"]:
        raise CalibrationError("settings_invalid", "定姿等待上限须覆盖准备和采样窗口")
    return defaults


def _dot(a, b):
    return sum(x*y for x,y in zip(a,b))


def _norm(a):
    return math.hypot(*a)


def _unit(a):
    length = _norm(a)
    if length < 1e-9:
        raise CalibrationError("degenerate_vector", "方向向量退化，需重新采集")
    return tuple(v/length for v in a)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _vector(value, field):
    if (not isinstance(value, (list,tuple)) or len(value) != 3 or
            any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value)):
        raise CalibrationError("invalid_sample", "标定样本无效："+field)
    return tuple(value)


def _samples(values, settings, kind):
    if not isinstance(values, (list,tuple)):
        raise CalibrationError("invalid_window", "标定窗口必须为完整样本列表")
    minimum = settings["neutral_min_samples"] if kind == "neutral" else settings["motion_min_samples"]
    duration = settings["neutral_min_seconds"] if kind == "neutral" else settings["motion_min_seconds"]
    if len(values) < minimum:
        raise CalibrationError("insufficient_samples", "有效数据不足，请确认连接后重新采样", {"samples":len(values),"minimum":minimum})
    result = []
    previous = None
    for source in values:
        if not isinstance(source,dict):
            raise CalibrationError("invalid_sample", "标定样本必须为对象")
        stamp = source.get("time",source.get("received_monotonic",source.get("timestamp")))
        if isinstance(stamp,bool) or not isinstance(stamp,(float,int)) or not math.isfinite(stamp):
            raise CalibrationError("invalid_clock", "标定样本时间无效")
        if previous is not None and not 0 <= stamp-previous <= settings["maximum_sample_gap_s"]+1e-9:
            raise CalibrationError("sample_gap", "样本失鲜或时钟不连续，需重新采集", {"gap_s":stamp-previous})
        if previous is not None and stamp == previous:
            raise CalibrationError("duplicate_clock", "重复采样时刻不能增加标定窗口样本数")
        previous = stamp
        try:
            q = quaternion(source["quaternion"])
        except (ValueError,KeyError,TypeError) as exc:
            raise CalibrationError("invalid_quaternion", "标定姿态无效") from exc
        accel, gyro = _vector(source.get("accel"),"accel"), _vector(source.get("gyro"),"gyro")
        flags = source.get("sensor_flags",source.get("flags",1))
        if not isinstance(flags,int) or flags & 1 != 1 or source.get("valid",True) is False:
            raise CalibrationError("invalid_sample", "标定包含无效传感器样本")
        if _norm(accel) > 200 or _norm(gyro) > 4000:
            raise CalibrationError("invalid_sample", "标定包含超范围传感器样本")
        result.append({**source,"time":float(stamp),"quaternion":q,"accel":accel,"gyro":gyro})
    span = result[-1]["time"]-result[0]["time"]
    if span < duration-1e-9:
        raise CalibrationError("insufficient_duration", "采样时间不足，请重新采集并保持姿态稳定", {"duration_s":span,"minimum_s":duration})
    return result


def _identity(neutral, motion):
    metadata = {}
    for key in IDENTITY_FIELDS:
        observed = {json.dumps(s[key],sort_keys=True) for s in (*neutral,*motion) if key in s}
        if len(observed) > 1:
            raise CalibrationError("identity_changed", "标定期间设备/角色/启动会话/处理参考变化："+key)
        if observed:
            metadata[key] = json.loads(next(iter(observed)))
    return metadata


def summarize_neutral(neutral_samples, *, config=None, tolerant=False):
    settings = load_settings(config)
    samples = _samples(neutral_samples,settings,"neutral")
    # Validate every original frame/identity before excluding physical noise.
    # Historical motion analysis deliberately keeps its original strict rule.
    _identity(samples, [])
    input_samples = samples
    excluded_indices = []
    speeds = [_norm(s["gyro"]) for s in samples]
    mean_gyro = _norm(tuple(sum(s["gyro"][i] for s in samples)/len(samples) for i in range(3)))
    if tolerant:
        if mean_gyro > settings["neutral_max_gyro_dps"] or median(speeds) > settings["static_inlier_gyro_dps"]:
            raise CalibrationError("neutral_not_stationary",
                f"中立窗口角速度持续偏大（平均向量模长 {mean_gyro:.2f}°/s、中位模长 {median(speeds):.2f}°/s）；请放稳，持续偏大时先做零偏校准",
                {"residual_gyro_mean_dps":mean_gyro,"residual_gyro_median_dps":median(speeds),
                 "mean_limit_dps":settings["neutral_max_gyro_dps"],"median_limit_dps":settings["static_inlier_gyro_dps"]})
        if max(speeds) > settings["static_hard_gyro_dps"]:
            raise CalibrationError("neutral_not_stationary", "中立窗口有明显转动，继续保持姿态等待稳定窗口",
                                   {"residual_gyro_peak_dps":max(speeds)})
        center = mean([s["quaternion"] for s in samples])
        excluded_indices = [i for i,s in enumerate(samples)
                            if speeds[i] > settings["static_inlier_gyro_dps"]
                            or not settings["neutral_accel_min_g"] <= _norm(s["accel"]) <= settings["neutral_accel_max_g"]
                            or angle_degrees(center,s["quaternion"]) > settings["neutral_max_spread_deg"]]
        if len(excluded_indices) > len(samples)*settings["static_outlier_fraction"]+1e-9:
            raise CalibrationError("neutral_not_stationary", "中立窗口晃动较多，继续放稳；不是要求绝对静止",
                                   {"outlier_samples":len(excluded_indices),"input_samples":len(samples)})
        excluded = set(excluded_indices)
        samples = _samples([s for i,s in enumerate(samples) if i not in excluded],settings,"neutral")
    elif any(_norm(s["gyro"]) > settings["neutral_max_gyro_dps"] or
           not settings["neutral_accel_min_g"] <= _norm(s["accel"]) <= settings["neutral_accel_max_g"] for s in samples):
        raise CalibrationError("neutral_not_stationary", "中立窗口不静止或重力异常；先检查残余角速度/安装并重采")
    q0 = mean([s["quaternion"] for s in samples])
    spread = max(angle_degrees(q0,s["quaternion"]) for s in samples)
    if spread > settings["neutral_max_spread_deg"]:
        raise CalibrationError("neutral_orientation_unstable", "中立姿态窗口不稳定，不能作为安装参考", {"spread_deg":spread})
    average_accel = tuple(sum(s["accel"][i] for s in samples)/len(samples) for i in range(3))
    gravity = _unit(average_accel)
    accel_spread = math.sqrt(sum(_norm(tuple(a-b for a,b in zip(s["accel"],average_accel)))**2 for s in samples)/len(samples))
    if accel_spread > .04:
        raise CalibrationError("neutral_gravity_unstable", "中立窗口加速度变化过大；请保持静止", {"accel_spread_g":accel_spread})
    return {"reference":q0,"gravity_sensor":gravity,
            "quality":{"samples":len(samples),"duration_s":samples[-1]["time"]-samples[0]["time"],
                       "quaternion_spread_deg":spread,"accel_spread_g":accel_spread,
                       "residual_gyro_peak_dps":max(_norm(s["gyro"]) for s in samples),
                       "residual_gyro_median_dps":median(speeds),
                       "residual_gyro_mean_dps":mean_gyro,
                       "input_samples":len(input_samples),"excluded_samples":len(excluded_indices),
                       "excluded_indices":excluded_indices,"input_residual_gyro_peak_dps":max(speeds)}}


def _log_vector(q):
    q = quaternion(q)
    if q[0] < 0:
        q = tuple(-v for v in q)
    vector = q[1:]
    length = _norm(vector)
    if length < 1e-10:
        return (0.,0.,0.)
    angle = 2*math.atan2(length,max(0.,q[0]))
    return tuple(math.degrees(angle)*v/length for v in vector)


def _matrix_quaternion(rows):
    """Quaternion of a proper 3x3 active rotation (row-major)."""
    r = rows
    trace = r[0][0]+r[1][1]+r[2][2]
    if trace > 0:
        scale = math.sqrt(trace+1.)*2
        return quaternion((.25*scale,(r[2][1]-r[1][2])/scale,(r[0][2]-r[2][0])/scale,(r[1][0]-r[0][1])/scale))
    index = max(range(3),key=lambda i:r[i][i])
    if index == 0:
        scale = math.sqrt(max(0.,1+r[0][0]-r[1][1]-r[2][2]))*2
        return quaternion(((r[2][1]-r[1][2])/scale,.25*scale,(r[0][1]+r[1][0])/scale,(r[0][2]+r[2][0])/scale))
    if index == 1:
        scale = math.sqrt(max(0.,1+r[1][1]-r[0][0]-r[2][2]))*2
        return quaternion(((r[0][2]-r[2][0])/scale,(r[0][1]+r[1][0])/scale,.25*scale,(r[1][2]+r[2][1])/scale))
    scale = math.sqrt(max(0.,1+r[2][2]-r[0][0]-r[1][1]))*2
    return quaternion(((r[1][0]-r[0][1])/scale,(r[0][2]+r[2][0])/scale,(r[1][2]+r[2][1])/scale,.25*scale))


def fit_direction(neutral_samples, motion_samples, *, config=None):
    """Fit one full declared-forward raise/return, or raise CalibrationError.

    gyro must be the independently bias-corrected observation *before* any
    stationary hold zeros it. Quaternions must be un-zeroed fusion output, not
    display attitude. Neither input is modified. Window summaries stay compact;
    DirectionSession saves full input windows separately with a content hash.
    """
    settings = load_settings(config)
    neutral = _samples(neutral_samples,settings,"neutral")
    motion = _samples(motion_samples,settings,"motion")
    metadata = _identity(neutral,motion)
    neutral_summary = summarize_neutral(neutral,config=settings)
    q0, vertical = neutral_summary["reference"],neutral_summary["gravity_sensor"]
    if motion[0]["time"] < neutral[-1]["time"]:
        raise CalibrationError("window_order", "动作窗口必须位于中立采集之后")
    vectors = [_log_vector(multiply(inverse(q0),s["quaternion"])) for s in motion]
    magnitudes = [_norm(v) for v in vectors]
    amplitude = max(magnitudes)
    if amplitude < settings["motion_min_excursion_deg"]:
        raise CalibrationError("insufficient_excursion", "动作幅度不足以辨识方向；缓慢前举后放回，无需精确指定角度", {"excursion_deg":amplitude})
    if amplitude > settings["motion_max_excursion_deg"]:
        raise CalibrationError("ambiguous_excursion", "动作超过本标定的单次小于半周约束，请减小幅度重采", {"excursion_deg":amplitude})
    significant = [v for v in vectors if _norm(v) >= max(5.,amplitude*.2)]
    if len(significant) < 15:
        raise CalibrationError("insufficient_motion_window", "有效运动窗口不足；不能仅用一个终点姿态标定")
    axis = _unit(significant[0])
    # Principal axis of quaternion-log observations; no external linear-algebra
    # dependency. The sign comes from the *first* outward excursion, never from
    # an arbitrary eigenvector sign or a hardware/device-specific convention.
    for _ in range(24):
        axis = _unit(tuple(sum(v[i]*_dot(v,axis) for v in significant) for i in range(3)))
    if _dot(axis,significant[0]) < 0:
        axis = tuple(-v for v in axis)
    projections = [_dot(v,axis) for v in vectors]
    reverse = max(0.,-min(projections))
    if reverse > settings["motion_max_reverse_excursion_deg"]:
        raise CalibrationError("opposite_excursions", "动作窗口包含相反方向或多次摆动；只前举一次并放回", {"reverse_excursion_deg":reverse})
    residuals = [_norm(tuple(v[i]-_dot(v,axis)*axis[i] for i in range(3))) for v in significant]
    axis_residual = math.sqrt(sum(value*value for value in residuals)/len(residuals))
    if axis_residual > settings["motion_max_axis_residual_deg"]:
        raise CalibrationError("non_hinge_motion", "方向动作不符合单一转轴，或融合参考在窗口内变化；保持肘伸直并重采", {"axis_residual_deg":axis_residual})
    vertical_dot = abs(_dot(axis,vertical))
    if vertical_dot > settings["motion_max_axis_vertical_dot"]:
        raise CalibrationError("axis_gravity_contradiction", "动作转轴与中立重力的几何关系矛盾；不是约定的前举，请检查动作和传感器", {"axis_vertical_dot":vertical_dot})
    peak_index = max(range(len(projections)),key=projections.__getitem__)
    if peak_index < 5 or len(projections)-peak_index < 10:
        raise CalibrationError("missing_raise_or_return", "缺少完整前举或放回过程，需采集整个往返窗口")
    # Compare actual bias-corrected gyro with orientation excursion before any
    # hold zeroing. A changing AHRS reference must not masquerade as a limb turn.
    rates = [_dot(rotate(s["gyro"],multiply(inverse(q0),s["quaternion"])),axis) for s in motion]
    integrated_raise = sum((rates[i]+rates[i-1])*.5*(motion[i]["time"]-motion[i-1]["time"])
                           for i in range(1,peak_index+1))
    observed_raise = projections[peak_index]-projections[0]
    gyro_error = abs(integrated_raise-observed_raise)
    if gyro_error > max(settings["motion_gyro_integral_error_deg"],settings["motion_gyro_integral_error_ratio"]*observed_raise):
        raise CalibrationError("gyro_orientation_contradiction", "原始残余角速度与姿态变化不一致；检查偏置、停稳和融合参考变化后重采",
                               {"gyro_integral_deg":integrated_raise,"orientation_excursion_deg":observed_raise,"error_deg":gyro_error})
    total_path = sum(abs(b-a) for a,b in zip(projections,projections[1:]))
    path_ratio = total_path/max(1.,2*max(projections))
    if path_ratio > settings["motion_max_path_ratio"]:
        raise CalibrationError("multiple_or_noisy_motion", "运动窗口反复摆动或噪声/漂移过大，需单次平稳往返", {"path_ratio":path_ratio})
    rest_seconds = settings["motion_end_rest_seconds"]
    tail = [s for s in motion if s["time"] >= motion[-1]["time"]-rest_seconds-1e-9]
    if len(tail) < 5 or tail[-1]["time"]-tail[0]["time"] < rest_seconds*.8:
        raise CalibrationError("missing_end_rest", "放回后静止观察窗口不足")
    if any(_norm(s["gyro"]) > settings["neutral_max_gyro_dps"] or not settings["neutral_accel_min_g"] <= _norm(s["accel"]) <= settings["neutral_accel_max_g"] for s in tail):
        raise CalibrationError("return_not_stationary", "放回后的样本仍在运动或重力异常，需保持静止再结束")
    returned = mean([s["quaternion"] for s in tail])
    return_error = angle_degrees(q0,returned)
    if return_error > settings["motion_return_max_error_deg"]:
        raise CalibrationError("return_or_drift_error", "未放回中立姿态，或窗口内漂移/融合参考变化过大", {"return_error_deg":return_error})
    end_spread = max(angle_degrees(returned,s["quaternion"]) for s in tail)
    if end_spread > settings["neutral_max_spread_deg"]:
        raise CalibrationError("return_orientation_unstable", "放回后的姿态窗口不稳定")
    # TRIAD: body Z expressed in neutral sensor frame, body Y is opposite the
    # signed forward-raise axis, body X=Y cross Z. Project only after checking
    # the original geometric residual rather than forcing any data to pass.
    horizontal = _unit(tuple(axis[i]-_dot(axis,vertical)*vertical[i] for i in range(3)))
    sensor_y = tuple(-v for v in horizontal)
    sensor_x = _unit(_cross(sensor_y,vertical))
    sensor_y = _unit(_cross(vertical,sensor_x))
    sensor_to_body = _matrix_quaternion((sensor_x,sensor_y,vertical))
    alignment = multiply(sensor_to_body,inverse(q0))
    mount = inverse(sensor_to_body)
    warnings = []
    if return_error > settings["motion_return_warning_deg"]:
        warnings.append("回零残差较大：方向参考不能消除航向漂移，建议复查静置和磁场策略")
    quality = {"neutral":neutral_summary["quality"],"motion_samples":len(motion),
               "motion_duration_s":motion[-1]["time"]-motion[0]["time"],
               "excursion_deg":amplitude,"axis_residual_deg":axis_residual,
               "axis_vertical_dot":vertical_dot,"reverse_excursion_deg":reverse,
               "path_ratio":path_ratio,"return_error_deg":return_error,
               "gyro_raise_integral_deg":integrated_raise,"gyro_orientation_error_deg":gyro_error,
               "end_spread_deg":end_spread,"warnings":warnings,
               "direction_label_verified_by_sensor":False,
               "amplitude_ground_truth_required":False}
    return {"schema_version":SCHEMA_VERSION,"algorithm_version":ALGORITHM_VERSION,
            "coordinates":{"world":"X-forward,Y-left,Z-up","quaternion":"wxyz","handedness":"right"},
            "reference":q0,"sensor_to_body":sensor_to_body,
            "fusion_to_world":alignment,"mount_bone_to_sensor":mount,
            "gravity_sensor":vertical,"forward_raise_axis_sensor":axis,
            "metadata":metadata,"quality":quality,"settings":settings,
            "windows":{"neutral":{"samples":len(neutral),"start":neutral[0]["time"],"end":neutral[-1]["time"]},
                       "forward_raise_return":{"samples":len(motion),"start":motion[0]["time"],"end":motion[-1]["time"]}},
            "assumptions":["中立骨段自然下垂，人体前方由操作者明确约定", "采集一次缓慢前举并放回，肘伸直、无明显躯干转动", "窗口内融合参考和传感器安装保持固定", "功能动作标定不等于磁标定、零偏校准或漂移消除"],
            "validation_required":["未参与拟合的再次前举", "未参与拟合的向外侧举", "上臂稳定时独立屈肘"]}


def fit_static_direction(neutral_samples, forward_samples, *, config=None):
    """Two stationary poses, with an externally declared straight-arm front raise.

    Q0^-1 Q1 = C^-1 R(-Y,theta) C: its principal log has a signed
    C^-1(-Y) axis for 0 < theta < pi. Neutral gravity supplies C^-1 Z.
    The user supplies the anatomical direction and pure-hinge constraint;
    two endpoints cannot establish the intervening path or remove yaw drift.
    Legacy fit_direction remains available for explicit historical analysis.
    """
    settings = load_settings(config)
    neutral = _samples(neutral_samples, settings, "neutral")
    forward = _samples(forward_samples, settings, "neutral")
    metadata = _identity(neutral, forward)
    first = summarize_neutral(neutral, config=settings, tolerant=True)
    try:
        second = summarize_neutral(forward, config=settings, tolerant=True)
    except CalibrationError as exc:
        raise CalibrationError(exc.code, str(exc).replace("中立", "前举定姿")+"；停稳后重新点击前举采样", exc.quality) from exc
    if forward[0]["time"] <= neutral[-1]["time"]:
        raise CalibrationError("window_order", "请先采中立，再抬臂停稳采前举")
    q0, q1 = first["reference"], second["reference"]
    relative = multiply(inverse(q0), q1)
    vector = _log_vector(relative)
    amplitude = _norm(vector)
    if amplitude < settings["motion_min_excursion_deg"]:
        raise CalibrationError("insufficient_excursion", "抬臂幅度太小，请再向正前方抬高一些，停稳后重采前举；不用摆准角度", {"excursion_deg": amplitude})
    if amplitude > settings["motion_max_excursion_deg"]:
        raise CalibrationError("ambiguous_excursion", "抬臂接近半周，方向不易区分；降低手臂后停稳重采前举", {"excursion_deg": amplitude})
    axis, vertical = _unit(vector), first["gravity_sensor"]
    vertical_dot = abs(_dot(axis, vertical))
    if vertical_dot > settings["motion_max_axis_vertical_dot"]:
        raise CalibrationError("axis_gravity_contradiction", "两次姿态含明显扭转；保持躯干不动、肘伸直，重新采中立和正前举", {"axis_vertical_dot": vertical_dot})
    predicted = rotate(vertical, inverse(relative))
    gravity_error = math.degrees(math.acos(max(-1., min(1., _dot(predicted, second["gravity_sensor"])))))
    if gravity_error > settings["static_max_gravity_error_deg"]:
        raise CalibrationError("gravity_orientation_contradiction", "重力与姿态变化不一致；检查数据和偏置，重新采两次定姿", {"gravity_error_deg": gravity_error})
    horizontal = _unit(tuple(axis[i]-_dot(axis, vertical)*vertical[i] for i in range(3)))
    sensor_y = tuple(-v for v in horizontal)
    sensor_x = _unit(_cross(sensor_y, vertical))
    sensor_y = _unit(_cross(vertical, sensor_x))
    installation = _matrix_quaternion((sensor_x, sensor_y, vertical))
    return {"schema_version": "functional-installation/2", "algorithm_version": "gravity-two-static-poses/3",
            "coordinates": {"world": "X-forward,Y-left,Z-up", "quaternion": "wxyz", "handedness": "right"},
            "reference": q0, "sensor_to_body": installation,
            "fusion_to_world": multiply(installation, inverse(q0)), "mount_bone_to_sensor": inverse(installation),
            "gravity_sensor": vertical, "forward_raise_axis_sensor": axis, "metadata": metadata,
            "quality": {"neutral": first["quality"], "forward": second["quality"],
                        "excursion_deg": amplitude, "axis_vertical_dot": vertical_dot, "gravity_error_deg": gravity_error,
                        "direction_label_verified_by_sensor": False, "intermediate_path_observed": False,
                        "warnings": ["两次定姿不能核实中间动作路径、人体前方或消除航向漂移；应用后请验证侧举和屈肘"]},
            "settings": settings,
            "windows": {name: {"samples": len(samples), "start": samples[0]["time"], "end": samples[-1]["time"]}
                        for name, samples in (("neutral", neutral), ("forward_static", forward))},
            "assumptions": ["中立两段自然下垂、肘伸直", "前举时躯干稳定、肘伸直、无附加扭转，人体前方由用户约定",
                            "两次采样间安装和融合参考保持固定", "定姿标定不等于零偏、磁标定或漂移消除"],
            "validation_required": ["侧举", "再次前举", "独立屈肘"]}
