from __future__ import annotations

from collections import defaultdict, deque

from mocap_pose.domain.models import NodePose, SynchronizedPoseFrame
from mocap_pose.math.quaternion import slerp


class FrameBuilder:
    def __init__(
        self,
        expected_nodes: tuple[int, ...] = tuple(range(1, 15)),
        stale_after_us: int = 100_000,
        interpolation_limit_us: int = 50_000,
    ) -> None:
        self.expected_nodes = expected_nodes
        self.stale_after_us = stale_after_us
        self.interpolation_limit_us = interpolation_limit_us
        self._history: dict[int, deque[NodePose]] = defaultdict(lambda: deque(maxlen=32))

    def add(self, pose: NodePose) -> None:
        history = self._history[pose.node_id]
        if history and pose.frame_time_us < history[-1].frame_time_us:
            ordered = sorted((*history, pose), key=lambda value: value.frame_time_us)
            history.clear()
            history.extend(ordered[-history.maxlen :])
        else:
            history.append(pose)

    def _pose_at(self, node_id: int, target_us: int) -> NodePose | None:
        history = self._history.get(node_id)
        if not history:
            return None
        before = max(
            (value for value in history if value.frame_time_us <= target_us),
            default=None,
            key=lambda pose: pose.frame_time_us,
        )
        after = min(
            (value for value in history if value.frame_time_us >= target_us),
            default=None,
            key=lambda pose: pose.frame_time_us,
        )
        if before and after and before is not after:
            span = after.frame_time_us - before.frame_time_us
            if 0 < span <= self.interpolation_limit_us:
                fraction = (target_us - before.frame_time_us) / span
                return NodePose(
                    node_id,
                    target_us,
                    slerp(before.quaternion_wxyz, after.quaternion_wxyz, fraction),
                    before.quality + fraction * (after.quality - before.quality),
                    0.0,
                    before.status_flags | after.status_flags,
                )
        chosen = before or after
        if chosen is None:
            return None
        return NodePose(
            chosen.node_id,
            target_us,
            chosen.quaternion_wxyz,
            chosen.quality,
            abs(target_us - chosen.frame_time_us) / 1000,
            chosen.status_flags,
        )

    def build(self, target_us: int) -> SynchronizedPoseFrame:
        poses: dict[int, NodePose] = {}
        missing: list[int] = []
        stale: list[int] = []
        for node_id in self.expected_nodes:
            pose = self._pose_at(node_id, target_us)
            if pose is None:
                missing.append(node_id)
                continue
            poses[node_id] = pose
            if pose.data_age_ms * 1000 > self.stale_after_us:
                stale.append(node_id)
        availability = len(poses) / len(self.expected_nodes) if self.expected_nodes else 1.0
        freshness = 1.0 - len(stale) / len(self.expected_nodes) if self.expected_nodes else 1.0
        return SynchronizedPoseFrame(
            target_us,
            poses,
            tuple(missing),
            tuple(stale),
            max(0.0, min(1.0, availability * freshness)),
        )
