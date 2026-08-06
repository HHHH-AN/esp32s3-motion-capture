import math

import pytest

from mocap_pose.domain.models import NodePose
from mocap_pose.math.quaternion import from_axis_angle
from mocap_pose.synchronization.clock_model import ClockModel
from mocap_pose.synchronization.frame_builder import FrameBuilder
from mocap_pose.synchronization.reorder_buffer import ReorderBuffer


def test_clock_model_estimates_offset_and_drift() -> None:
    model = ClockModel()
    for index in range(50):
        device = index * 10_000
        host = round(1_000_000 + 1.0001 * device)
        model.update(device, host)
    assert model.ready
    assert model.slope == pytest.approx(1.0001, abs=2e-6)
    assert model.to_host_time(750_000) == pytest.approx(1_750_075, abs=2)
    assert model.rms_error_us < 1


def test_reorder_buffer_releases_in_timestamp_order() -> None:
    buffer = ReorderBuffer[str](window_us=10)
    assert buffer.push(20, "b") == []
    assert buffer.push(10, "a") == ["a"]
    assert buffer.push(35, "c") == ["b"]
    assert buffer.flush() == ["c"]


def test_frame_builder_interpolates_quaternion_and_marks_missing() -> None:
    builder = FrameBuilder(expected_nodes=(1, 2), stale_after_us=100_000)
    builder.add(NodePose(1, 0, (1.0, 0.0, 0.0, 0.0), 1.0, 0.0))
    builder.add(NodePose(1, 20_000, from_axis_angle((0.0, 0.0, 1.0), math.pi / 2), 0.8, 0.0))
    frame = builder.build(10_000)
    assert frame.missing_nodes == (2,)
    assert frame.poses[1].quaternion_wxyz[0] == pytest.approx(math.cos(math.pi / 8), abs=1e-6)
    assert frame.synchronization_quality == pytest.approx(0.5)

