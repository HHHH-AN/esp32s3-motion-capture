from dataclasses import dataclass

from mocap_pose.domain.models import Vector3


@dataclass(frozen=True, slots=True)
class SegmentSpec:
    segment_id: str
    start_joint_id: str
    end_joint_id: str
    node_id: int | None
    length_m: float
    direction_local: Vector3
    virtual: bool = False


@dataclass(frozen=True, slots=True)
class SkeletonProfile:
    profile_id: str
    root_joint_id: str
    root_node_id: int
    segments: tuple[SegmentSpec, ...]
    expected_nodes: tuple[int, ...]

