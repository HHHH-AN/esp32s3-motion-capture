"""Strict right-handed WXYZ rotations shared by calibration and the body solver.

All rotations are active: multiply(a,b) applies b, then a. No Euler-angle
subtraction is used anywhere in the body processing chain.
"""
from __future__ import annotations

import math

IDENTITY = (1., 0., 0., 0.)


def quaternion(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("四元数必须为 WXYZ 四项")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value):
        raise ValueError("四元数含无效数值")
    length = math.hypot(*value)
    if length < 1e-9:
        raise ValueError("拒绝零四元数")
    return tuple(v/length for v in value)


def inverse(value):
    w, x, y, z = quaternion(value)
    return w, -x, -y, -z


def multiply(a, b):
    w, x, y, z = quaternion(a)
    v, i, j, k = quaternion(b)
    return quaternion((w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                       w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v))


def rotate(vector, q):
    w, x, y, z = quaternion(q)
    vx, vy, vz = vector
    tx, ty, tz = 2*(y*vz-z*vy), 2*(z*vx-x*vz), 2*(x*vy-y*vx)
    return (vx+w*tx+y*tz-z*ty, vy+w*ty+z*tx-x*tz, vz+w*tz+x*ty-y*tx)


def mean(quaternions):
    items = [quaternion(q) for q in quaternions]
    if not items:
        raise ValueError("姿态平均没有样本")
    reference = items[0]
    aligned = [q if sum(a*b for a, b in zip(q, reference)) >= 0 else tuple(-v for v in q) for q in items]
    return quaternion(tuple(sum(q[i] for q in aligned) for i in range(4)))


def angle_degrees(a, b):
    a, b = quaternion(a), quaternion(b)
    if sum(x*y for x,y in zip(a,b)) < 0:
        b = tuple(-v for v in b)
    # Chord lengths avoid acos cancellation for almost-identical rotations.
    return math.degrees(4*math.atan2(math.hypot(*(x-y for x,y in zip(a,b))),
                                    math.hypot(*(x+y for x,y in zip(a,b)))))


def slerp(a, b, amount):
    a, b = quaternion(a), quaternion(b)
    dot = sum(x*y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-v for v in b), -dot
    amount = min(1., max(0., amount))
    if dot > .9995:
        return quaternion(tuple(x+amount*(y-x) for x, y in zip(a, b)))
    theta = math.acos(min(1., dot))
    scale = math.sin(theta)
    return quaternion(tuple((math.sin((1-amount)*theta)*x+math.sin(amount*theta)*y)/scale for x, y in zip(a, b)))


def add(a, b):
    return tuple(x+y for x, y in zip(a, b))
