import json
from pathlib import Path

import pytest

from mocap_pose.api.schemas import SkeletonFrameMessage
from mocap_pose.domain.models import NodePose, SynchronizedPoseFrame
from mocap_pose.skeleton.kinematics import SkeletonKinematics
from mocap_pose.skeleton.layout import default_human14_profile, load_profile


def identity_poses() -> dict[int, NodePose]:
    return {node: NodePose(node, 1000, (1.0, 0.0, 0.0, 0.0), 1.0, 0.0) for node in range(1, 15)}


def test_t_pose_forward_kinematics_and_message_shape() -> None:
    solver = SkeletonKinematics(default_human14_profile())
    result = solver.solve(SynchronizedPoseFrame(1000, identity_poses()))
    joints = {joint.joint_id: joint for joint in result.joints}
    assert joints["chest"].position_m == pytest.approx((0.0, 0.0, 0.48))
    assert joints["left_elbow"].position_m == pytest.approx((0.0, 0.50, 0.48))
    assert joints["right_knee"].position_m == pytest.approx((0.0, -0.10, -0.42))
    message = result.to_message()
    assert message["type"] == "skeleton.frame.v1"
    assert message["schema_version"] == 1
    assert isinstance(message["joints"], list)
    assert isinstance(message["segments"], list)
    virtual_chest = next(
        segment for segment in message["segments"] if segment["segment_id"] == "virtual_chest"
    )
    assert virtual_chest["virtual"]
    assert SkeletonFrameMessage.model_validate(message).schema_version == 1


def test_missing_node_invalidates_only_its_descendant_chain() -> None:
    poses = identity_poses()
    del poses[3]
    result = SkeletonKinematics(default_human14_profile()).solve(
        SynchronizedPoseFrame(1000, poses, missing_nodes=(3,))
    )
    joints = {joint.joint_id: joint for joint in result.joints}
    assert not joints["left_elbow"].valid
    assert not joints["left_wrist"].valid
    assert joints["right_elbow"].valid


def test_repository_profile_is_loadable_when_present() -> None:
    path = Path(__file__).parents[3] / "contracts" / "profiles" / "human-14-v1.json"
    assert path.exists()
    assert "segment_id" in json.loads(path.read_text())["segments"][0]
    profile = load_profile(path)
    assert profile == default_human14_profile()
    assert profile.expected_nodes == tuple(range(1, 15))
    assert {item.node_id for item in profile.segments if item.node_id} >= set(range(1, 15))
