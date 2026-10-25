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


def mean_axis_std(vectors):
    count = len(vectors)
    mean = tuple(sum(vector[i] for vector in vectors)/count for i in range(3))
    spread = tuple(math.sqrt(sum((vector[i]-mean[i])**2 for vector in vectors)/count)
                   for i in range(3))
    return mean, spread


def mean_std(vectors):
    mean, axes = mean_axis_std(vectors)
    return mean, norm(axes)


class AttitudeStabilizer:
    CALIBRATION_SECONDS = 4.0
    SETTLE_SECONDS = .8
    CALIBRATION_TIMEOUT = 30.
    REST_SECONDS = .6
    REST_GYRO_DPS = .8
    REST_MEAN_DPS = .12
    GYRO_AXIS_STD_LIMIT_DPS = .45
    GYRO_MEAN_CHANGE_LIMIT_DPS = .25

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
        self.phase = 'idle'
        self.retries = 0
        self._request_started = self._settle_until = None
        self._wait_reason = ''
        self._samples = deque(maxlen=1200)
        self._window = deque(maxlen=150)
        self._device_us = self._arrival = self._started = None
        self._elapsed = self._clock = 0.

    def start_calibration(self, now=None):
        # Keep a previously successful bias until a replacement is accepted.
        self.calibrating, self.stationary = True, False
        self.progress = 0.
        self.message = "等待放稳：准备后连续静置 4 秒，运动时会自动重试"
        self.phase, self.retries = 'waiting', 0
        self._request_started = now
        self._settle_until = None if now is None else now+self.SETTLE_SECONDS
        self._wait_reason = ''
        self.calibration_quality = {}
        self._samples.clear()
        self._window.clear()
        self._device_us = self._arrival = self._started = None
        self._elapsed = self._clock = 0.

    def reset_window(self, reason=""):
        if self.calibrating:
            self.message = "校准取消："+(reason or "数据不连续，请重试")
            self.phase = 'cancelled'
        self.calibrating = self.stationary = False
        self.progress = 0.
        self._samples.clear()
        self._window.clear()
        self._device_us = self._arrival = self._started = None
        self._elapsed = self._clock = 0.
        self._request_started = self._settle_until = None

    def expire(self, now):
        if self.calibrating and self._request_started is not None and now-self._request_started >= self.CALIBRATION_TIMEOUT:
            reason = self._wait_reason or '未得到连续稳定样本'
            self.reset_window('30秒内未完成：'+reason+'；请放稳后重试')
            self.phase = 'failed'
            return True
        return False

    def _wait_for_still(self, reason, now):
        if self._samples:
            self.retries += 1
        self._samples.clear()
        self._started, self._elapsed = None, 0.
        self.progress, self.phase = 0., 'waiting'
        self._settle_until = now+self.SETTLE_SECONDS
        self._wait_reason = reason
        self.message = '等待放稳：'+reason+'；静置后自动重新采集'

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
            # TCP may deliver continuous device samples in batches. A host
            # scheduling delay alone is not evidence of a sensor-time gap.
            if arrival_dt < 0 or not 0 <= dt <= .2:
                self.reset_window("采样中断或设备重启，请重新静置校准")
                dt = 0.
        self._arrival, self._device_us = now, sample.device_us
        self._clock += dt
        if self.calibrating:
            if self._request_started is None:
                self._request_started = now
                self._settle_until = now+self.SETTLE_SECONDS
            if self.expire(now):
                return False
            gyro_norm = norm(sample.gyro)
            accel_norm = norm(sample.accel)
            self.calibration_quality['last_observation'] = {'gyro_norm_dps': gyro_norm, 'accel_norm_g': accel_norm}
            if not .85 <= accel_norm <= 1.15:
                self._wait_for_still(f'加速度 {accel_norm:.2f}g，仍有移动或振动', now)
                return False
            if gyro_norm > 10 or (not sample.sensor_flags & 2 and gyro_norm > 3):
                self._wait_for_still(f'角速度 {gyro_norm:.1f}°/s 过大；若已静止请保持放稳后重新上电', now)
                return False
            if now < self._settle_until-1e-9:
                self.message = '等待放稳：'+(self._wait_reason or '请松开板子')+'；准备后自动采集4秒'
                return False
            if self._started is None:
                self._started = now
                dt = 0.
            self.phase = 'collecting'
            self._elapsed += dt
            self._samples.append(sample)
            wall_elapsed = now-self._started
            elapsed = min(wall_elapsed, self._elapsed)
            self.progress = min(1., elapsed/self.CALIBRATION_SECONDS)
            self.message = f"静置校准中 {min(elapsed, 4):.1f}/4 秒 · {len(self._samples)} 帧"
            if elapsed >= self.CALIBRATION_SECONDS-1e-9 and len(self._samples) >= 200:
                gyros = [item.gyro for item in self._samples]
                bias, gyro_axes_std = mean_axis_std(gyros)
                gyro_std = norm(gyro_axes_std)
                block = max(1, len(gyros)//8)
                first_gyro, _ = mean_std(gyros[:block])
                last_gyro, _ = mean_std(gyros[-block:])
                gyro_mean_change = norm(tuple(a-b for a, b in zip(first_gyro, last_gyro)))
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
                    # Uncorrelated magnetic noise is not proof of movement.
                    # Preserve coherent direction-change rejection, and let
                    # guard_magnetometer gate noisy heading after gyro bias
                    # succeeds. Gyro calibration is not magnetic calibration.
                    magnetic_motion = 50 <= norm(mag_mean) <= 1500 and mag_direction_change > 3
                self.calibration_quality = {"samples": len(self._samples), "duration_s": elapsed,
                                            "gyro_std_dps": gyro_std, "accel_std_g": accel_std,
                                            "gyro_axis_std_dps": gyro_axes_std,
                                            "gyro_max_axis_std_dps": max(gyro_axes_std),
                                            "gyro_axis_std_limit_dps": self.GYRO_AXIS_STD_LIMIT_DPS,
                                            "gyro_mean_change_dps": gyro_mean_change,
                                            "mag_relative_std": mag_relative_std,
                                            "mag_std_mG": mag_std,
                                            "mag_direction_change_deg": mag_direction_change,
                                            "magnetic_noisy": mag_relative_std is not None and mag_relative_std > .05}
                if (max(gyro_axes_std) > self.GYRO_AXIS_STD_LIMIT_DPS or
                        gyro_mean_change > self.GYRO_MEAN_CHANGE_LIMIT_DPS or
                        accel_std > .01 or magnetic_motion):
                    if max(gyro_axes_std) > self.GYRO_AXIS_STD_LIMIT_DPS:
                        reason = f'角速度单轴波动 {max(gyro_axes_std):.3f}°/s，超过{self.GYRO_AXIS_STD_LIMIT_DPS:.2f}（振动或噪声偏大）'
                    elif gyro_mean_change > self.GYRO_MEAN_CHANGE_LIMIT_DPS:
                        reason = f'角速度均值变化 {gyro_mean_change:.3f}°/s，需继续静置或等待预热稳定'
                    elif accel_std > .01:
                        reason = f'加速度波动 {accel_std:.3f}g，超过0.01'
                    else:
                        reason = '磁场方向或强度仍在变化，请远离磁性物体'
                    self._wait_for_still(reason, now)
                    return False
                self.bias, self._gravity = bias, norm(accel_mean)
                magnetic_strength = (sum(norm(item) for item in magnetic)/len(magnetic)) if len(magnetic) >= 200 else None
                self._mag_reference = magnetic_strength if magnetic_strength is not None and 50 <= magnetic_strength <= 1500 else None
                self._mag_noise = mag_std
                self.calibrated, self.calibrating = True, False
                self.phase = 'complete'
                self.progress = 1.
                self.message = "零偏校准完成；安装/站姿参考须由上层重新确认"
                if self.calibration_quality["magnetic_noisy"]:
                    self.message += "；磁场噪声偏大，航向观测将按质量门控"
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
        gyro_mean, gyro_axes_std = mean_axis_std([item[2] for item in self._window])
        self.stationary = (len(self._window) >= 20 and span >= self.REST_SECONDS-1e-9
                           and accel_std <= .008 and norm(gyro_mean) <= self.REST_MEAN_DPS
                           and max(gyro_axes_std) <= self.GYRO_AXIS_STD_LIMIT_DPS)
        return False
