from __future__ import annotations

import math
from dataclasses import dataclass

from .models import NodeState, SensorSample


Vector = tuple[float, float, float]
REST: dict[str, Vector] = {
    "head": (0, 2.50, 0), "_face": (0, 2.50, .30), "_neck": (0, 2.20, 0), "_chest": (0, 1.66, 0),
    "waist": (0, .68, 0), "_pelvis": (0, .25, 0),
    "left_shoulder": (-.58, 1.92, 0), "left_elbow": (-1.12, 1.37, 0), "left_wrist": (-1.52, .83, 0),
    "right_shoulder": (.58, 1.92, 0), "right_elbow": (1.12, 1.37, 0), "right_wrist": (1.52, .83, 0),
    "_left_hand_tip": (-1.79, .47, 0), "_right_hand_tip": (1.79, .47, 0),
    "left_hip": (-.34, .18, 0), "left_knee": (-.38, -.98, 0), "left_ankle": (-.40, -2.02, .05),
    "right_hip": (.34, .18, 0), "right_knee": (.38, -.98, 0), "right_ankle": (.40, -2.02, .05),
    "_left_toe": (-.40, -2.02, .48), "_right_toe": (.40, -2.02, .48),
}


def add(a: Vector, b: Vector) -> Vector:
    return tuple(x + y for x, y in zip(a, b))  # type: ignore[return-value]


def sub(a: Vector, b: Vector) -> Vector:
    return tuple(x - y for x, y in zip(a, b))  # type: ignore[return-value]


def rotate(vector: Vector, q: tuple[float, float, float, float]) -> Vector:
    w, x, y, z = q
    vx, vy, vz = vector
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def solve_positions(nodes: dict[str, NodeState]) -> dict[str, Vector]:
    positions = dict(REST)

    def segment(parent: str, child: str, driver: str) -> None:
        direction = sub(REST[child], REST[parent])
        node = nodes.get(driver)
        if node and node.source == "real" and node.valid:
            direction = rotate(direction, node.quaternion)
        positions[child] = add(positions[parent], direction)

    for args in (
        ("waist", "_pelvis", "waist"), ("waist", "_chest", "waist"),
        ("_chest", "_neck", "waist"), ("_neck", "head", "head"), ("head", "_face", "head"),
        ("_chest", "left_shoulder", "left_shoulder"), ("left_shoulder", "left_elbow", "left_shoulder"),
        ("left_elbow", "left_wrist", "left_elbow"), ("left_wrist", "_left_hand_tip", "left_wrist"),
        ("_chest", "right_shoulder", "right_shoulder"),
        ("right_shoulder", "right_elbow", "right_shoulder"), ("right_elbow", "right_wrist", "right_elbow"),
        ("right_wrist", "_right_hand_tip", "right_wrist"),
        ("_pelvis", "left_hip", "left_hip"), ("left_hip", "left_knee", "left_hip"),
        ("left_knee", "left_ankle", "left_knee"), ("left_ankle", "_left_toe", "left_ankle"),
        ("_pelvis", "right_hip", "right_hip"),
        ("right_hip", "right_knee", "right_hip"), ("right_knee", "right_ankle", "right_knee"),
        ("right_ankle", "_right_toe", "right_ankle"),
    ):
        segment(*args)
    positions["_chest"] = ((positions["left_shoulder"][0] + positions["right_shoulder"][0]) / 2,
                           positions["_chest"][1], positions["_chest"][2])
    positions["_neck"] = (positions["_chest"][0], positions["_neck"][1], positions["_neck"][2])
    positions["_pelvis"] = ((positions["left_hip"][0] + positions["right_hip"][0]) / 2,
                            positions["_pelvis"][1], positions["_pelvis"][2])
    return positions


@dataclass
class ShortTermBodyTracker:
    """Bounded inertial trend estimate; deliberately not an absolute position."""

    position: Vector = (0.0, 0.0, 0.0)
    velocity: Vector = (0.0, 0.0, 0.0)
    last_time: float | None = None

    def reset(self) -> None:
        self.position, self.velocity, self.last_time = (0, 0, 0), (0, 0, 0), None

    def update(self, sample: SensorSample | None, quaternion: tuple[float, float, float, float] | None) -> Vector:
        if sample is None or quaternion is None:
            return self.position
        now = sample.received_monotonic
        dt = .02 if self.last_time is None else min(max(now - self.last_time, .001), .1)
        self.last_time = now
        world_accel = rotate(sample.accel, quaternion)
        # The current firmware/library commonly reports m/s². Remove gravity;
        # suppress noise and decay velocity so this remains a short-term trend.
        acceleration = (world_accel[0], world_accel[1], world_accel[2] - 9.80665)
        acceleration = tuple(0.0 if abs(v) < .18 else max(-12.0, min(12.0, v)) for v in acceleration)
        self.velocity = tuple((v + a * dt) * .94 for v, a in zip(self.velocity, acceleration))  # type: ignore[assignment]
        self.position = tuple(max(-3.0, min(3.0, p + v * dt)) for p, v in zip(self.position, self.velocity))  # type: ignore[assignment]
        return self.position
