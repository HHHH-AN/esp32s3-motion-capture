"""Explicit per-device gyro calibration and conservative rest detection.

Rest is a threshold-based assumption, not an independent measurement. We never
learn bias automatically from ordinary movement. Values use the mapped sensor
frame and deg/s, g, mG; no displacement estimator is involved.
"""
from collections import deque
from dataclasses import replace
import math


def norm(values):
    return math.sqrt(sum(value*value for value in values))


def mean_std(vectors):
    count = len(vectors)
    mean = tuple(sum(vector[i] for vector in vectors)/count for i in range(3))
    spread = math.sqrt(sum(sum((vector[i]-mean[i])**2 for i in range(3))
                           for vector in vectors)/count)
    return mean, spread


class AttitudeStabilizer:
    CALIBRATION_SECONDS = 4.0
    REST_SECONDS = .6
    REST_GYRO_DPS = .8
    REST_MEAN_DPS = .12

    def __init__(self):
        self.clear()

    def clear(self):
        self.bias = (0., 0., 0.)
        self.calibrated = self.calibrating = self.stationary = False
        self.progress = 0.
        self.message = "未校准：请将板子放稳，点击静置校准"
        self._gravity = 1.
        self._mag_reference = None
        self._mag_noise = None
        self.magnetic_used = False
        self.magnetic_message = "等待磁场观测"
        self.calibration_quality = {}
        self._samples = deque(maxlen=1200)
        self._window = deque(maxlen=150)
        self._device_us = self._arrival = self._started = None
        self._elapsed = self._clock = 0.

    def start_calibration(self):
        # Keep a previously successful bias until a replacement is accepted.
        self.calibrating, self.stationary = True, False
        self.progress = 0.
        self.message = "请保持板子静止至少 4 秒；校准后自动设置显示参考"
        self.calibration_quality = {}
        self._samples.clear()
        self._window.clear()
        self._device_us = self._arrival = self._started = None
        self._elapsed = self._clock = 0.

    def reset_window(self, reason=""):
        if self.calibrating:
            self.message = "校准取消："+(reason or "数据不连续，请重试")
        self.calibrating = self.stationary = False
        self.progress = 0.
        self._samples.clear()
        self._window.clear()
        self._device_us = self._arrival = self._started = None
        self._elapsed = self._clock = 0.

    def corrected(self, sample):
        return replace(sample, gyro=tuple(value-bias for value, bias in zip(sample.gyro, self.bias)))

    def guard_magnetometer(self, sample):
        strength = norm(sample.mag)
        self.magnetic_used = bool(sample.sensor_flags & 2)
        self.magnetic_message = "使用磁场观测；尚未做完整磁标定"
        if not self.magnetic_used:
            self.magnetic_message = "磁力计无效：使用六轴，航向会累积漂移"
        elif not 50 <= strength <= 1500 or (self._mag_reference is not None and
                not .65 <= strength/self._mag_reference <= 1.35):
            self.magnetic_used = False
            self.magnetic_message = "磁场强度异常：暂时跳过航向修正"
        elif .8 <= norm(sample.accel) <= 1.2:
            # Heading uses the horizontal field, not the whole field magnitude.
            # A large vertical field can look healthy while horizontal noise
            # dominates azimuth. Use the observed calibration noise as a
            # conservative signal/noise gate; it is not a magnetic calibration.
            vertical = sum(a*m for a, m in zip(sample.accel, sample.mag))/norm(sample.accel)
            horizontal = math.sqrt(max(0., strength*strength-vertical*vertical))
            if horizontal < 1 or (self._mag_noise is not None and self._mag_noise/max(horizontal, 1e-6) > .05):
                self.magnetic_used = False
                self.magnetic_message = "磁航向噪声较大：暂用六轴，停稳后保持朝向"
        return sample if self.magnetic_used else replace(sample, sensor_flags=sample.sensor_flags & ~2)

    def update(self, sample):
        """Observe one sample; return True only when a calibration is accepted."""
        now = sample.received_monotonic
        dt = 0.
        if self._arrival is not None:
            arrival_dt = now-self._arrival
            dt = arrival_dt
            if sample.device_us is not None and self._device_us is not None:
                dt = ((sample.device_us-self._device_us) % 2**32)/1e6
            if not 0 <= arrival_dt <= .2 or not 0 <= dt <= .2:
                self.reset_window("采样中断或设备重启，请重新静置校准")
                dt = 0.
        self._arrival, self._device_us = now, sample.device_us
        self._clock += dt
        if self.calibrating:
            gyro_norm = norm(sample.gyro)
            if (not .85 <= norm(sample.accel) <= 1.15 or gyro_norm > 10
                    or (not sample.sensor_flags & 2 and gyro_norm > 3)):
                self.reset_window("检测到明显运动，请将板子放稳后重试")
                return False
            if self._started is None:
                self._started = now
            self._elapsed += dt
            self._samples.append(sample)
            wall_elapsed = now-self._started
            elapsed = min(wall_elapsed, self._elapsed)
            self.progress = min(1., elapsed/self.CALIBRATION_SECONDS)
            self.message = f"静置校准中 {min(elapsed, 4):.1f}/4 秒 · {len(self._samples)} 帧"
            if wall_elapsed > 12:
                self.reset_window("有效采样不足，请检查连接后重试")
                return False
            if elapsed >= self.CALIBRATION_SECONDS-1e-9 and len(self._samples) >= 200:
                bias, gyro_std = mean_std([item.gyro for item in self._samples])
                accel_mean, accel_std = mean_std([item.accel for item in self._samples])
                magnetic = [item.mag for item in self._samples if item.sensor_flags & 2 and norm(item.mag) > 1e-6]
                magnetic_motion = False
                mag_relative_std = None
                mag_direction_change = None
                mag_std = None
                if len(magnetic) >= 200:
                    mag_mean, mag_std = mean_std(magnetic)
                    mag_relative_std = mag_std/max(norm(mag_mean), 1e-6)
                    # Average endpoint blocks to distinguish a heading trend
                    # from uncorrelated magnetometer noise during a still hold.
                    block = max(1, len(magnetic)//8)
                    first_mag, _ = mean_std(magnetic[:block])
                    last_mag, _ = mean_std(magnetic[-block:])
                    cosine = sum(a*b for a, b in zip(first_mag, last_mag))/max(norm(first_mag)*norm(last_mag), 1e-9)
                    mag_direction_change = math.degrees(math.acos(max(-1., min(1., cosine))))
                    magnetic_motion = mag_relative_std > .05 or mag_direction_change > 3
                self.calibration_quality = {"samples": len(self._samples), "duration_s": elapsed,
                                            "gyro_std_dps": gyro_std, "accel_std_g": accel_std,
                                            "mag_relative_std": mag_relative_std,
                                            "mag_std_mG": mag_std,
                                            "mag_direction_change_deg": mag_direction_change}
                if gyro_std > .35 or accel_std > .01 or magnetic_motion:
                    self.reset_window("样本不稳定或磁场变化，请静置并远离磁性物体后重试")
                    return False
                self.bias, self._gravity = bias, norm(accel_mean)
                magnetic_strength = (sum(norm(item) for item in magnetic)/len(magnetic)) if len(magnetic) >= 200 else None
                self._mag_reference = magnetic_strength if magnetic_strength is not None and 50 <= magnetic_strength <= 1500 else None
                self._mag_noise = mag_std
                self.calibrated, self.calibrating = True, False
                self.progress = 1.
                self.message = "零偏校准完成；已自动设置当前显示参考"
                self._samples.clear()
                self._window.clear()
                return True
            return False
        if not self.calibrated:
            self.stationary = False
            return False
        corrected = self.corrected(sample)
        # A motion sample releases the hold immediately, without waiting for the
        # rest window to expire. Sub-threshold motion remains a stated limit.
        if norm(corrected.gyro) > self.REST_GYRO_DPS or abs(norm(sample.accel)-self._gravity) > .06:
            self.stationary = False
            self._window.clear()
            return False
        self._window.append((self._clock, sample.accel, corrected.gyro))
        while len(self._window) > 2 and self._window[1][0] <= self._clock-self.REST_SECONDS:
            self._window.popleft()
        span = self._clock-self._window[0][0]
        _, accel_std = mean_std([item[1] for item in self._window])
        gyro_mean, gyro_std = mean_std([item[2] for item in self._window])
        self.stationary = (len(self._window) >= 20 and span >= self.REST_SECONDS-1e-9
                           and accel_std <= .008 and norm(gyro_mean) <= self.REST_MEAN_DPS
                           and gyro_std <= .35)
        return False
