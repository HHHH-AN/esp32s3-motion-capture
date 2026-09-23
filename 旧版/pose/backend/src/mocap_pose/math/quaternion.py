from __future__ import annotations

import math

from mocap_pose.domain.models import Quaternion, Vector3

IDENTITY: Quaternion = (1.0, 0.0, 0.0, 0.0)


def normalize(q: Quaternion) -> Quaternion:
    length = math.sqrt(sum(value * value for value in q))
    if length < 1e-12:
        raise ValueError("zero-length quaternion")
    return tuple(value / length for value in q)  # type: ignore[return-value]


def conjugate(q: Quaternion) -> Quaternion:
    return q[0], -q[1], -q[2], -q[3]


def inverse(q: Quaternion) -> Quaternion:
    norm_sq = sum(value * value for value in q)
    if norm_sq < 1e-12:
        raise ValueError("zero-length quaternion")
    return tuple(value / norm_sq for value in conjugate(q))  # type: ignore[return-value]


def multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def rotate_vector(q: Quaternion, vector: Vector3) -> Vector3:
    rotated = multiply(multiply(normalize(q), (0.0, *vector)), conjugate(normalize(q)))
    return rotated[1], rotated[2], rotated[3]


def from_axis_angle(axis: Vector3, angle_rad: float) -> Quaternion:
    length = math.sqrt(sum(value * value for value in axis))
    if length < 1e-12:
        raise ValueError("axis must be non-zero")
    sine = math.sin(angle_rad / 2) / length
    return normalize((math.cos(angle_rad / 2), axis[0] * sine, axis[1] * sine, axis[2] * sine))


def slerp(a: Quaternion, b: Quaternion, fraction: float) -> Quaternion:
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between zero and one")
    qa, qb = normalize(a), normalize(b)
    dot = sum(left * right for left, right in zip(qa, qb, strict=True))
    if dot < 0:
        qb = tuple(-value for value in qb)  # type: ignore[assignment]
        dot = -dot
    dot = min(1.0, dot)
    if dot > 0.9995:
        interpolated = tuple(
            a_ + fraction * (b_ - a_) for a_, b_ in zip(qa, qb, strict=True)
        )
        return normalize(interpolated)  # type: ignore[arg-type]
    theta = math.acos(dot)
    sine = math.sin(theta)
    left_weight = math.sin((1 - fraction) * theta) / sine
    right_weight = math.sin(fraction * theta) / sine
    return tuple(
        left_weight * a_ + right_weight * b_ for a_, b_ in zip(qa, qb, strict=True)
    )  # type: ignore[return-value]
