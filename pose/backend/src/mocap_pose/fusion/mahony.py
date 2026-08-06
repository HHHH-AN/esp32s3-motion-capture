from __future__ import annotations

import math

from mocap_pose.domain.models import Quaternion, Vector3
from mocap_pose.math.quaternion import IDENTITY, normalize


def _unit(vector: Vector3) -> Vector3 | None:
    length = math.sqrt(sum(value * value for value in vector))
    if length < 1e-12 or not math.isfinite(length):
        return None
    return tuple(value / length for value in vector)  # type: ignore[return-value]


class MahonyFilter:
    def __init__(self, kp: float = 1.0, ki: float = 0.02) -> None:
        self.kp = kp
        self.ki = ki
        self.quaternion: Quaternion = IDENTITY
        self._integral = [0.0, 0.0, 0.0]

    def reset(self, quaternion: Quaternion = IDENTITY) -> None:
        self.quaternion = normalize(quaternion)
        self._integral[:] = (0.0, 0.0, 0.0)

    def update(
        self,
        gyro_rad_s: Vector3,
        accel_m_s2: Vector3,
        mag_ut: Vector3,
        dt_s: float,
        use_magnetometer: bool = True,
    ) -> Quaternion:
        if not 0 < dt_s <= 0.5:
            raise ValueError("dt_s must be in (0, 0.5]")
        accel = _unit(accel_m_s2)
        mag = _unit(mag_ut) if use_magnetometer else None
        gx, gy, gz = gyro_rad_s
        q0, q1, q2, q3 = self.quaternion

        if accel is not None:
            ax, ay, az = accel
            half_vx = q1 * q3 - q0 * q2
            half_vy = q0 * q1 + q2 * q3
            half_vz = q0 * q0 - 0.5 + q3 * q3
            ex = ay * half_vz - az * half_vy
            ey = az * half_vx - ax * half_vz
            ez = ax * half_vy - ay * half_vx

            if mag is not None:
                mx, my, mz = mag
                hx = 2 * (
                    mx * (0.5 - q2 * q2 - q3 * q3)
                    + my * (q1 * q2 - q0 * q3)
                    + mz * (q1 * q3 + q0 * q2)
                )
                hy = 2 * (
                    mx * (q1 * q2 + q0 * q3)
                    + my * (0.5 - q1 * q1 - q3 * q3)
                    + mz * (q2 * q3 - q0 * q1)
                )
                bx = math.sqrt(hx * hx + hy * hy)
                bz = 2 * (
                    mx * (q1 * q3 - q0 * q2)
                    + my * (q2 * q3 + q0 * q1)
                    + mz * (0.5 - q1 * q1 - q2 * q2)
                )
                half_wx = bx * (0.5 - q2 * q2 - q3 * q3) + bz * (q1 * q3 - q0 * q2)
                half_wy = bx * (q1 * q2 - q0 * q3) + bz * (q0 * q1 + q2 * q3)
                half_wz = bx * (q0 * q2 + q1 * q3) + bz * (0.5 - q1 * q1 - q2 * q2)
                ex += my * half_wz - mz * half_wy
                ey += mz * half_wx - mx * half_wz
                ez += mx * half_wy - my * half_wx

            if self.ki > 0:
                self._integral[0] += self.ki * ex * dt_s
                self._integral[1] += self.ki * ey * dt_s
                self._integral[2] += self.ki * ez * dt_s
                gx += self._integral[0]
                gy += self._integral[1]
                gz += self._integral[2]
            gx += self.kp * ex
            gy += self.kp * ey
            gz += self.kp * ez

        half_dt = 0.5 * dt_s
        self.quaternion = normalize(
            (
                q0 + (-q1 * gx - q2 * gy - q3 * gz) * half_dt,
                q1 + (q0 * gx + q2 * gz - q3 * gy) * half_dt,
                q2 + (q0 * gy - q1 * gz + q3 * gx) * half_dt,
                q3 + (q0 * gz + q1 * gy - q2 * gx) * half_dt,
            )
        )
        return self.quaternion

