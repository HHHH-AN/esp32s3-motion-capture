from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from mocap_pose.domain.models import NodePose, Quaternion
from mocap_pose.math.quaternion import normalize


def average_mounting_poses(frames: Iterable[dict[int, NodePose]]) -> dict[int, Quaternion]:
    """Quaternion average with hemisphere correction for a stationary T-pose capture."""
    values: dict[int, list[Quaternion]] = defaultdict(list)
    for frame in frames:
        for node_id, pose in frame.items():
            values[node_id].append(pose.quaternion_wxyz)
    output: dict[int, Quaternion] = {}
    for node_id, quaternions in values.items():
        reference = quaternions[0]
        aligned = [
            q
            if sum(a * b for a, b in zip(reference, q, strict=True)) >= 0
            else tuple(-v for v in q)
            for q in quaternions
        ]
        output[node_id] = normalize(
            tuple(sum(q[index] for q in aligned) for index in range(4))  # type: ignore[arg-type]
        )
    return output
