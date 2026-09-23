from __future__ import annotations

import math

from .models import SensorSample


Quaternion = tuple[float, float, float, float]


def normalize(q: Quaternion) -> Quaternion:
    length = math.sqrt(sum(value * value for value in q))
    if length < 1e-9:
        return (1.0, 0.0, 0.0, 0.0)
    return tuple(value / length for value in q)  # type: ignore[return-value]


def euler_quaternion(roll: float, pitch: float, yaw: float) -> Quaternion:
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return normalize((
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ))


def nlerp(a: Quaternion, b: Quaternion, amount: float) -> Quaternion:
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = tuple(-value for value in b)  # type: ignore[assignment]
    return normalize(tuple(x + amount * (y - x) for x, y in zip(a, b)))  # type: ignore[arg-type]


class ComplementaryFusion:
    """Small, dependency-free gyro integration with accel/mag drift correction."""

    def __init__(self) -> None:
        self.q: Quaternion = (1.0, 0.0, 0.0, 0.0)
        self.last_time: float | None = None

    def reset(self) -> None:
        self.q = (1.0, 0.0, 0.0, 0.0)
        self.last_time = None

    def update(self, sample: SensorSample) -> Quaternion:
        now = sample.received_monotonic
        dt = 0.02 if self.last_time is None else min(max(now - self.last_time, 0.001), 0.1)
        self.last_time = now

        gx, gy, gz = (math.radians(value) for value in sample.gyro)
        w, x, y, z = self.q
        derivative = (
            -0.5 * (x * gx + y * gy + z * gz),
            0.5 * (w * gx + y * gz - z * gy),
            0.5 * (w * gy - x * gz + z * gx),
            0.5 * (w * gz + x * gy - y * gx),
        )
        predicted = normalize(tuple(value + delta * dt for value, delta in zip(self.q, derivative)))  # type: ignore[arg-type]

        ax, ay, az = sample.accel
        accel_norm = math.sqrt(ax * ax + ay * ay + az * az)
        if accel_norm < 1e-6:
            self.q = predicted
            return self.q
        roll = math.atan2(ay, az)
        pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))

        mx, my, mz = sample.mag
        mag_norm = math.sqrt(mx * mx + my * my + mz * mz)
        if mag_norm > 1e-6:
            mx2 = mx * math.cos(pitch) + mz * math.sin(pitch)
            my2 = (mx * math.sin(roll) * math.sin(pitch) + my * math.cos(roll)
                   - mz * math.sin(roll) * math.cos(pitch))
            yaw = math.atan2(-my2, mx2)
            correction = 0.015
        else:
            yaw = math.atan2(2 * (predicted[0] * predicted[3] + predicted[1] * predicted[2]),
                             1 - 2 * (predicted[2] ** 2 + predicted[3] ** 2))
            correction = 0.008
        self.q = nlerp(predicted, euler_quaternion(roll, pitch, yaw), correction)
        return self.q

