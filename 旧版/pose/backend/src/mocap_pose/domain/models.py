from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

Vector3: TypeAlias = tuple[float, float, float]
Quaternion: TypeAlias = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class IngressPacket:
    data: bytes
    arrival_time_us: int
    transport: str


@dataclass(frozen=True, slots=True)
class RawImuSample:
    node_id: int
    sequence: int
    device_timestamp_us: int
    accel_mg: tuple[int, int, int]
    gyro_dps_x10: tuple[int, int, int]
    mag_ut_x10: tuple[int, int, int]
    temperature_c_x100: int
    mag_age_us: int
    status_flags: int


@dataclass(frozen=True, slots=True)
class CalibratedImuSample:
    node_id: int
    sequence: int
    device_timestamp_us: int
    accel_m_s2: Vector3
    gyro_rad_s: Vector3
    mag_ut: Vector3
    temperature_c: float
    mag_age_us: int
    status_flags: int


@dataclass(frozen=True, slots=True)
class NodePose:
    node_id: int
    frame_time_us: int
    quaternion_wxyz: Quaternion
    quality: float
    data_age_ms: float
    status_flags: int = 0

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "pose.frame.v1",
            "schema_version": 1,
            "node_id": self.node_id,
            "frame_time_us": self.frame_time_us,
            "quaternion_wxyz": list(self.quaternion_wxyz),
            "quality": self.quality,
            "data_age_ms": self.data_age_ms,
            "status_flags": self.status_flags,
        }


@dataclass(frozen=True, slots=True)
class SynchronizedPoseFrame:
    frame_time_us: int
    poses: dict[int, NodePose]
    missing_nodes: tuple[int, ...] = ()
    stale_nodes: tuple[int, ...] = ()
    synchronization_quality: float = 1.0


@dataclass(frozen=True, slots=True)
class JointPose:
    joint_id: str
    parent_joint_id: str | None
    position_m: Vector3
    world_rotation_wxyz: Quaternion
    valid: bool
    data_age_ms: float
    virtual: bool = False
    node_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "joint_id": self.joint_id,
            "parent_joint_id": self.parent_joint_id,
            "position_m": list(self.position_m),
            "world_rotation_wxyz": list(self.world_rotation_wxyz),
            "valid": self.valid,
            "data_age_ms": self.data_age_ms,
            "virtual": self.virtual,
        }
        if self.node_id is not None:
            value["node_id"] = self.node_id
        return value


@dataclass(frozen=True, slots=True)
class SegmentPose:
    segment_id: str
    start_joint_id: str
    end_joint_id: str
    virtual: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "start_joint_id": self.start_joint_id,
            "end_joint_id": self.end_joint_id,
            "virtual": self.virtual,
        }


@dataclass(frozen=True, slots=True)
class SkeletonFrame:
    frame_time_us: int
    root_position_m: Vector3
    joints: tuple[JointPose, ...]
    segments: tuple[SegmentPose, ...]
    missing_nodes: tuple[int, ...] = ()
    stale_nodes: tuple[int, ...] = ()
    synchronization_quality: float = 1.0

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "skeleton.frame.v1",
            "schema_version": 1,
            "frame_time_us": self.frame_time_us,
            "root_position_m": list(self.root_position_m),
            "joints": [joint.to_dict() for joint in self.joints],
            "segments": [segment.to_dict() for segment in self.segments],
            "missing_nodes": list(self.missing_nodes),
            "stale_nodes": list(self.stale_nodes),
            "synchronization_quality": self.synchronization_quality,
        }


@dataclass(slots=True)
class DeviceState:
    node_id: int
    online: bool = True
    last_seen_us: int = 0
    packets_received: int = 0
    packets_lost: int = 0
    battery_mv: int | None = None
    charging: bool | None = None
    firmware_version: str | None = None
    errors: dict[str, int] = field(default_factory=dict)
