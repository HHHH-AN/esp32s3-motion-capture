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


def multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    w, x, y, z = a
    v, i, j, k = b
    return normalize((w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                      w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v))


def relative(q: Quaternion, origin: Quaternion) -> Quaternion:
    return multiply((origin[0], -origin[1], -origin[2], -origin[3]), q)


def euler_degrees(q: Quaternion) -> tuple[float, float, float]:
    w, x, y, z = q
    return tuple(math.degrees(value) for value in (
        math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)),
        math.asin(max(-1.0, min(1.0, 2*(w*y-z*x)))),
        math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))))


class ComplementaryFusion:
    """Small, dependency-free gyro integration with accel/mag drift correction."""

    def __init__(self, gravity_vector_correction: bool = False) -> None:
        self.gravity_vector_correction = gravity_vector_correction
        self.version = ("complementary-gravity-vector/2" if gravity_vector_correction
                        else "complementary-euler/1")
        self.q: Quaternion = (1.0, 0.0, 0.0, 0.0)
        self.last_time: float | None = None
        self.last_device_us: int | None = None

    def reset(self) -> None:
        self.q = (1.0, 0.0, 0.0, 0.0)
        self.last_time = None
        self.last_device_us = None

    def update(self, sample: SensorSample, correction_scale: float = 1.0) -> Quaternion:
        now = sample.received_monotonic
        first_update = self.last_time is None
        dt = 0.02 if self.last_time is None else min(max(now - self.last_time, 0.001), 0.1)
        if sample.device_us is not None and self.last_device_us is not None:
            elapsed = ((sample.device_us - self.last_device_us) % 2**32) / 1_000_000
            dt = min(max(elapsed, .001), .1)
        self.last_device_us = sample.device_us
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
        # Acceleration is in g. Reject strong dynamics as a gravity observation.
        if not .8 <= accel_norm <= 1.2:
            self.q = predicted
            return self.q
        roll = math.atan2(ay, az)
        pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))

        mx, my, mz = sample.mag
        mag_norm = math.sqrt(mx * mx + my * my + mz * mz)
        magnetic_observation = bool(sample.sensor_flags & 2 and mag_norm > 1e-6)
        if magnetic_observation:
            # Invert roll and pitch using the same Rz(yaw)Ry(pitch)Rx(roll)
            # convention as euler_quaternion. The old formula mixed conventions.
            mx2 = (mx * math.cos(pitch) + my * math.sin(pitch) * math.sin(roll)
                   + mz * math.sin(pitch) * math.cos(roll))
            my2 = my * math.cos(roll) - mz * math.sin(roll)
            yaw = math.atan2(-my2, mx2)
            correction = 1 - math.exp(-dt / 3.3)
        else:
            yaw = math.atan2(2 * (predicted[0] * predicted[3] + predicted[1] * predicted[2]),
                             1 - 2 * (predicted[2] ** 2 + predicted[3] ** 2))
            correction = 1 - math.exp(-dt / 6.2)
        observed = euler_quaternion(roll, pitch, yaw)
        if self.gravity_vector_correction and not magnetic_observation and not first_update:
            # Correct only the direction of gravity. Reconstructing an Euler
            # observation with the predicted Euler yaw couples tilt correction
            # into heading near vertical pitch and its +/-180 degree branches.
            # Rotate measured body gravity into the predicted world frame.
            axn, ayn, azn = ax/accel_norm, ay/accel_norm, az/accel_norm
            w, x, y, z = predicted
            ux = ((1-2*(y*y+z*z))*axn + 2*(x*y-w*z)*ayn + 2*(x*z+w*y)*azn)
            uy = (2*(x*y+w*z)*axn + (1-2*(x*x+z*z))*ayn + 2*(y*z-w*x)*azn)
            uz = (2*(x*z-w*y)*axn + 2*(y*z+w*x)*ayn + (1-2*(x*x+y*y))*azn)
            # The shortest world rotation taking u to +Z has a horizontal
            # rotation axis. At the exact antipode any horizontal axis works;
            # select +X deterministically rather than normalizing a zero q.
            if 1+uz < 1e-9 and math.hypot(ux, uy) < 1e-6:
                delta = (0., 1., 0., 0.)
            else:
                delta = normalize((1+uz, uy, -ux, 0.))
            observed = multiply(delta, predicted)
        self.q = observed if first_update else nlerp(predicted, observed, correction*correction_scale)
        return self.q

