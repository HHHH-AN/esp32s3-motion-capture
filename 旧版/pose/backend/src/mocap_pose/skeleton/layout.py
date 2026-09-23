from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import SegmentSpec, SkeletonProfile


def default_human14_profile() -> SkeletonProfile:
    segments = (
        SegmentSpec("virtual_chest", "pelvis", "chest", 1, 0.48, (0.0, 0.0, 1.0), True),
        SegmentSpec("head", "chest", "head", 2, 0.24, (0.0, 0.0, 1.0)),
        SegmentSpec("left_shoulder", "chest", "left_shoulder", 1, 0.20, (0.0, 1.0, 0.0), True),
        SegmentSpec("left_upper_arm", "left_shoulder", "left_elbow", 3, 0.30, (0.0, 1.0, 0.0)),
        SegmentSpec("left_forearm", "left_elbow", "left_wrist", 5, 0.26, (0.0, 1.0, 0.0)),
        SegmentSpec("left_hand", "left_wrist", "left_hand", 7, 0.18, (0.0, 1.0, 0.0)),
        SegmentSpec("right_shoulder", "chest", "right_shoulder", 1, 0.20, (0.0, -1.0, 0.0), True),
        SegmentSpec("right_upper_arm", "right_shoulder", "right_elbow", 4, 0.30, (0.0, -1.0, 0.0)),
        SegmentSpec("right_forearm", "right_elbow", "right_wrist", 6, 0.26, (0.0, -1.0, 0.0)),
        SegmentSpec("right_hand", "right_wrist", "right_hand", 8, 0.18, (0.0, -1.0, 0.0)),
        SegmentSpec("left_hip", "pelvis", "left_hip", 1, 0.10, (0.0, 1.0, 0.0), True),
        SegmentSpec("left_thigh", "left_hip", "left_knee", 9, 0.42, (0.0, 0.0, -1.0)),
        SegmentSpec("left_shank", "left_knee", "left_ankle", 11, 0.43, (0.0, 0.0, -1.0)),
        SegmentSpec("left_foot", "left_ankle", "left_toe", 13, 0.25, (1.0, 0.0, 0.0)),
        SegmentSpec("right_hip", "pelvis", "right_hip", 1, 0.10, (0.0, -1.0, 0.0), True),
        SegmentSpec("right_thigh", "right_hip", "right_knee", 10, 0.42, (0.0, 0.0, -1.0)),
        SegmentSpec("right_shank", "right_knee", "right_ankle", 12, 0.43, (0.0, 0.0, -1.0)),
        SegmentSpec("right_foot", "right_ankle", "right_toe", 14, 0.25, (1.0, 0.0, 0.0)),
    )
    return SkeletonProfile("human-14-v1", "pelvis", 1, segments, tuple(range(1, 15)))


def load_profile(path: Path) -> SkeletonProfile:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("skeleton profile schema_version must be 1")
    if value.get("coordinate_system") != "right-handed-x-forward-y-left-z-up":
        raise ValueError("skeleton profile uses an unsupported coordinate system")
    profile = SkeletonProfile(
        str(value.get("profile_id", value.get("id", "human-14-v1"))),
        str(value.get("root_joint_id", "pelvis")),
        int(value.get("root_node_id", 1)),
        tuple(
            SegmentSpec(
                str(item["segment_id"]),
                str(item["start_joint_id"]),
                str(item["end_joint_id"]),
                int(item["node_id"]) if item.get("node_id") is not None else None,
                float(item["length_m"]),
                tuple(float(v) for v in item["direction_local"]),  # type: ignore[arg-type]
                bool(item.get("virtual", False)),
            )
            for item in value["segments"]
        ),
        tuple(int(node) for node in value.get("expected_nodes", range(1, 15))),
    )
    validate_profile(profile)
    return profile


def load_default_profile() -> SkeletonProfile:
    configured = os.environ.get("MOCAP_PROFILE_PATH")
    if configured:
        return load_profile(Path(configured))
    repository_contract = (
        Path(__file__).resolve().parents[5]
        / "contracts"
        / "profiles"
        / "human-14-v1.json"
    )
    if repository_contract.exists():
        return load_profile(repository_contract)
    return default_human14_profile()


def validate_profile(profile: SkeletonProfile) -> None:
    known_joints = {profile.root_joint_id}
    segment_ids: set[str] = set()
    for segment in profile.segments:
        if segment.segment_id in segment_ids:
            raise ValueError(f"duplicate segment {segment.segment_id}")
        if segment.start_joint_id not in known_joints:
            raise ValueError(
                f"parent joint {segment.start_joint_id} is not defined before its child"
            )
        if segment.end_joint_id in known_joints:
            raise ValueError(f"joint {segment.end_joint_id} has multiple parents")
        if segment.length_m <= 0:
            raise ValueError(f"segment {segment.segment_id} has invalid length")
        if sum(value * value for value in segment.direction_local) <= 0:
            raise ValueError(f"segment {segment.segment_id} has zero direction")
        segment_ids.add(segment.segment_id)
        known_joints.add(segment.end_joint_id)
