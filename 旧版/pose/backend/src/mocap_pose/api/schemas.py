from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PoseFrameMessage(ContractModel):
    type: Literal["pose.frame.v1"] = "pose.frame.v1"
    schema_version: Literal[1] = 1
    node_id: int = Field(ge=1, le=14)
    frame_time_us: int = Field(ge=0)
    quaternion_wxyz: tuple[float, float, float, float]
    quality: float = Field(ge=0, le=1)
    data_age_ms: float = Field(ge=0)
    status_flags: int = Field(ge=0, le=65535)


class JointMessage(ContractModel):
    joint_id: str = Field(min_length=1)
    parent_joint_id: str | None
    position_m: tuple[float, float, float]
    world_rotation_wxyz: tuple[float, float, float, float]
    valid: bool
    data_age_ms: float = Field(ge=0)
    virtual: bool
    node_id: int | None = Field(default=None, ge=1, le=14)


class SegmentMessage(ContractModel):
    segment_id: str = Field(min_length=1)
    start_joint_id: str = Field(min_length=1)
    end_joint_id: str = Field(min_length=1)
    virtual: bool


class SkeletonFrameMessage(ContractModel):
    type: Literal["skeleton.frame.v1"] = "skeleton.frame.v1"
    schema_version: Literal[1] = 1
    frame_time_us: int = Field(ge=0)
    root_position_m: tuple[float, float, float]
    joints: list[JointMessage]
    segments: list[SegmentMessage]
    missing_nodes: list[int]
    stale_nodes: list[int]
    synchronization_quality: float = Field(ge=0, le=1)

    @field_validator("missing_nodes", "stale_nodes")
    @classmethod
    def validate_node_set(cls, value: list[int]) -> list[int]:
        if any(node < 1 or node > 14 for node in value):
            raise ValueError("node ids must be between 1 and 14")
        if len(set(value)) != len(value):
            raise ValueError("node ids must be unique")
        return value
