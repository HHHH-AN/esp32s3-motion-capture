"""Relative inertial position; sensor-frame rest detection is independent of AHRS."""
import math

from .kinematics import rotate
from collections import deque


def norm(vector):
    return math.sqrt(sum(v*v for v in vector))


class DisplacementEstimator:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = "idle"
        self.message = "等待连接后初始化位姿跟踪"
        self.position = (0.0, 0.0, 0.0)
        self.velocity = (0.0, 0.0, 0.0)
        self.linear_accel = (0.0, 0.0, 0.0)
        self.elapsed = 0.0
        self.duration = 10.0
        self.zupt = False
        self.stationary = False
        self.drift_mode = "balanced"
        self.accel_reference_g = 1.0
        self._sensor_window = deque()
        self._sensor_time = 0.0
        self.rest_window_s = self.accel_std_g = self.gyro_peak_dps = 0.0
        self._unconstrained_elapsed = 0.0
        self.zupt_count = 0
        self.sampling_gaps = 0
        self.last_gap_s = 0.0
        self._device_us = self._arrival = None
        self._baseline = []
        self._baseline_elapsed = self._still_elapsed = 0.0
        self._previous_accel = None

    @property
    def active(self):
        return self.phase in ("initializing", "measuring")

    def start(self, duration=10, zupt=False, drift_mode="faithful", preserve_position=False):
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not (duration == 0 or 2 <= duration <= 30):
            raise ValueError("跟踪时长应为 0（连续）或 2~30 秒")
        if not isinstance(zupt, bool):
            raise ValueError("静止速度归零开关需为布尔值")
        if drift_mode not in ("faithful", "balanced", "stable"):
            raise ValueError("请选择运动优先、均衡或稳定优先模式")
        position = self.position
        self.reset()
        if preserve_position:
            self.position = position
        self.duration, self.zupt = float(duration), zupt
        self.drift_mode = drift_mode
        self.phase, self.message = "initializing", "请静置板子约 1 秒，建立重力与零点基线"

    def stop(self, reason="位置跟踪已暂停，保留当前位置；姿态继续更新"):
        if self.active:
            self.phase, self.message = "stopped", reason

    def _observe_rest(self, sample, dt):
        """Heuristic rest candidate, not proof of zero physical velocity.

        Use a 0.3 s window of BODY-frame observations, never gravity-removed
        acceleration: a small tilt error must not prevent re-acquiring rest.
        Thresholds are starting heuristics, not a calibrated sensor noise model.
        Constant velocity/constant acceleration can still be indistinguishable
        from rest; disable ZUPT for such experiments.
        """
        self._sensor_time += dt
        self._sensor_window.append((self._sensor_time, sample.accel, norm(sample.gyro)))
        cutoff = self._sensor_time - .3
        while len(self._sensor_window) > 2 and self._sensor_window[1][0] <= cutoff:
            self._sensor_window.popleft()
        self.rest_window_s = self._sensor_time - self._sensor_window[0][0]
        count = len(self._sensor_window)
        mean = tuple(sum(item[1][i] for item in self._sensor_window)/count for i in range(3))
        self.accel_std_g = math.sqrt(sum(sum((item[1][i]-mean[i])**2 for i in range(3))
                                       for item in self._sensor_window)/count)
        self.gyro_peak_dps = max(item[2] for item in self._sensor_window)
        self.stationary = (self.rest_window_s >= .3-1e-9 and count >= 3
                           and abs(norm(mean)-self.accel_reference_g) < .06
                           and self.accel_std_g < .006 and self.gyro_peak_dps < 1.5)
        self._still_elapsed = self.rest_window_s if self.stationary else 0.0

    def update(self, sample, quaternion):
        if not self.active:
            return
        dt = 0.0
        if self._device_us is not None and sample.device_us is not None:
            dt = ((sample.device_us-self._device_us) % 2**32)/1e6
        elif self._arrival is not None:
            dt = sample.received_monotonic-self._arrival
        self._device_us, self._arrival = sample.device_us, sample.received_monotonic
        if dt < 0 or dt > .2:
            self.sampling_gaps += 1
            self.last_gap_s = round(dt, 3)
            if self.duration == 0 and dt >= 0:
                # Do not integrate across missing data or invent the missing motion.
                # Keep the last position; resume only after another static baseline.
                self.phase = "initializing"
                self.message = "采样缺口已跳过，位置保留；请静置约 1 秒自动恢复"
                self.velocity = self.linear_accel = (0.0, 0.0, 0.0)
                self.stationary = False
                self._still_elapsed = self._baseline_elapsed = self._unconstrained_elapsed = 0.0
                self._baseline.clear()
                self._sensor_window.clear()
                self._sensor_time = 0.0
                self.rest_window_s = self.accel_std_g = self.gyro_peak_dps = 0.0
                self._previous_accel = None
                self._device_us = self._arrival = None
            else:
                self.stop("采样间隔异常，估算已停止；请重新开始")
            return
        self._observe_rest(sample, dt)
        world = rotate(tuple(v*9.80665/self.accel_reference_g for v in sample.accel), quaternion)
        gravity_removed = (world[0], world[1], world[2]-9.80665)
        if self.phase == "initializing":
            if abs(norm(sample.accel)-1) > .08 or norm(sample.gyro) > 3:
                self._baseline.clear()
                self._baseline_elapsed = 0.0
                self.message = "检测到运动，请静置板子约 1 秒后再移动"
                return
            # A single static pose cannot distinguish lateral sensor bias from
            # attitude error. Learn magnitude only; never persist a 3D residual.
            self._baseline.append(norm(sample.accel))
            self._baseline_elapsed += dt
            if self._baseline_elapsed >= 1 and len(self._baseline) >= 30:
                count = len(self._baseline)
                mean = sum(self._baseline)/count
                variance = sum((v-mean)**2 for v in self._baseline)/count
                if math.sqrt(variance) > .015 or not self.stationary:
                    self._baseline.clear()
                    self._baseline_elapsed = 0.0
                    self.message = "基线不稳定，请继续静置或先校准零偏"
                    return
                self.accel_reference_g = mean
                self.phase, self.message = "measuring", "位姿连续跟踪中" if self.duration == 0 else "位姿片段跟踪中"
                self._previous_accel = (0.0, 0.0, 0.0)
                self._baseline.clear()
            return
        if dt == 0:
            return
        if self.duration > 0:
            dt = min(dt, max(0.0, self.duration-self.elapsed))
        accel = gravity_removed
        deadband, damping = {"faithful":(.08,0.0),"balanced":(.12,.08),"stable":(.20,.4)}[self.drift_mode]
        # A small deadband suppresses stationary noise; small accelerations are lost.
        self.linear_accel = tuple(0.0 if abs(v) < deadband else v for v in accel)
        old_velocity = self.velocity
        previous = self._previous_accel or self.linear_accel
        if self.zupt and self.stationary:
            if norm(self.velocity) > 1e-6:
                self.zupt_count += 1
            self.velocity = (0.0, 0.0, 0.0)
            self.linear_accel = (0.0, 0.0, 0.0)
            old_velocity = self.velocity
            self._unconstrained_elapsed = 0.0
            self.message = "停稳锁定：速度已归零，位置保持（原始传感器窗口判定）"
        else:
            self.velocity = tuple(v+(a+b)*.5*dt for v, a, b in zip(self.velocity, previous, self.linear_accel))
            if damping:
                self.velocity = tuple(v*math.exp(-damping*dt) for v in self.velocity)
            self._unconstrained_elapsed += dt
            self.message = ("静止修正已关闭：停下后不会自动清零残余速度" if not self.zupt else
                            "运动中或尚未停稳：惯性位姿估算" if self._unconstrained_elapsed < 10 else
                            "持续缺少静止约束，位置漂移风险升高；建议停稳修正")
        self.position = tuple(p+(v+w)*.5*dt for p,v,w in zip(self.position, old_velocity, self.velocity))
        self._previous_accel = self.linear_accel
        self.elapsed += dt
        if norm(self.velocity) > 20 or norm(self.position) > 100:
            self.stop("估算速度/位移越界，可能发生漂移；已停止")
        elif self.duration > 0 and self.elapsed >= self.duration-1e-9:
            self.stop("已到达设定时长；结果仅供短时趋势参考")

    def payload(self, coordinates, reference=(1,0,0,0)):
        inverse = (reference[0], -reference[1], -reference[2], -reference[3])
        display = lambda v: coordinates.display_vector(rotate(v,inverse))
        return {"phase":self.phase,"message":self.message,"active":self.active,
                "position":display(self.position),
                "velocity":display(self.velocity),
                "linear_accel":display(self.linear_accel),
                "distance":norm(self.position),"speed":norm(self.velocity),
                "elapsed_s":round(self.elapsed,3),"duration_s":self.duration,"zupt":self.zupt,
                "stationary":self.stationary,"drift_mode":self.drift_mode,"zupt_count":self.zupt_count,
                "rest_window_s":round(self.rest_window_s,3),"accel_std_g":round(self.accel_std_g,5),
                "gyro_peak_dps":round(self.gyro_peak_dps,3),"accel_reference_g":self.accel_reference_g,
                "sampling_gaps":self.sampling_gaps,"last_gap_s":self.last_gap_s,
                "quality":("inactive" if self.phase != "measuring" else
                           "stationary_constraint" if self.zupt and self.stationary else "inertial_only"),
                "unconstrained_s":round(self._unconstrained_elapsed,2)}
