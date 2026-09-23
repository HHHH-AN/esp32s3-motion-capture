from __future__ import annotations

from mocap_pose.domain.models import JointPose, SegmentPose, SkeletonFrame, SynchronizedPoseFrame
from mocap_pose.math.quaternion import IDENTITY, rotate_vector

from .layout import validate_profile
from .schema import SkeletonProfile


class SkeletonKinematics:
    def __init__(self, profile: SkeletonProfile) -> None:
        validate_profile(profile)
        self.profile = profile

    def solve(
        self,
        frame: SynchronizedPoseFrame,
        root_position_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> SkeletonFrame:
        root_pose = frame.poses.get(self.profile.root_node_id)
        root_rotation = root_pose.quaternion_wxyz if root_pose else IDENTITY
        root_valid = root_pose is not None and self.profile.root_node_id not in frame.stale_nodes
        joints: dict[str, JointPose] = {
            self.profile.root_joint_id: JointPose(
                self.profile.root_joint_id,
                None,
                root_position_m,
                root_rotation,
                root_valid,
                root_pose.data_age_ms if root_pose else 1_000_000_000.0,
                False,
                self.profile.root_node_id,
            )
        }
        segments: list[SegmentPose] = []
        for spec in self.profile.segments:
            parent = joints[spec.start_joint_id]
            pose = frame.poses.get(spec.node_id) if spec.node_id is not None else None
            rotation = pose.quaternion_wxyz if pose else parent.world_rotation_wxyz
            valid = parent.valid and (spec.virtual or pose is not None)
            if spec.node_id in frame.stale_nodes:
                valid = False
            direction = rotate_vector(rotation, spec.direction_local)
            position = tuple(
                parent.position_m[index] + direction[index] * spec.length_m for index in range(3)
            )
            joints[spec.end_joint_id] = JointPose(
                spec.end_joint_id,
                spec.start_joint_id,
                position,  # type: ignore[arg-type]
                rotation,
                valid,
                pose.data_age_ms if pose else parent.data_age_ms,
                spec.virtual,
                spec.node_id,
            )
            segments.append(
                SegmentPose(spec.segment_id, spec.start_joint_id, spec.end_joint_id, spec.virtual)
            )
        return SkeletonFrame(
            frame.frame_time_us,
            root_position_m,
            tuple(joints.values()),
            tuple(segments),
            frame.missing_nodes,
            frame.stale_nodes,
            frame.synchronization_quality,
        )
