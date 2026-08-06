from __future__ import annotations

from mocap_pose.domain.models import NodePose


class LatestPoseStore:
    """Keeps one replaceable pose per node; input rate never grows an output queue."""

    def __init__(self) -> None:
        self._poses: dict[int, NodePose] = {}

    def update(self, pose: NodePose) -> None:
        previous = self._poses.get(pose.node_id)
        if previous is None or pose.frame_time_us >= previous.frame_time_us:
            self._poses[pose.node_id] = pose

    def get(self, node_id: int) -> NodePose | None:
        return self._poses.get(node_id)

