import math

import pytest

from mocap_pose.domain.models import CalibratedImuSample
from mocap_pose.fusion.mahony import MahonyFilter
from mocap_pose.fusion.service import FusionService


def test_static_mahony_stays_normalized_and_level() -> None:
    fusion = MahonyFilter()
    for _ in range(1000):
        q = fusion.update((0.0, 0.0, 0.0), (0.0, 0.0, 9.80665), (45.0, 0.0, 10.0), 0.01)
    assert math.sqrt(sum(value * value for value in q)) == pytest.approx(1.0, abs=1e-6)
    assert q == pytest.approx((1.0, 0.0, 0.0, 0.0), abs=1e-4)


def test_service_integrates_ninety_degree_yaw_without_valid_magnetometer() -> None:
    service = FusionService()
    pose = None
    for index in range(100):
        sample = CalibratedImuSample(
            1,
            index,
            index * 10_000,
            (0.0, 0.0, 9.80665),
            (0.0, 0.0, math.pi / 2),
            (0.0, 0.0, 0.0),
            25.0,
            100_000,
            0x0007,
        )
        pose = service.update(sample)
    assert pose is not None
    assert abs(pose.quaternion_wxyz[0]) == pytest.approx(math.sqrt(0.5), abs=0.02)
    assert abs(pose.quaternion_wxyz[3]) == pytest.approx(math.sqrt(0.5), abs=0.02)
    assert pose.status_flags & 0x8000

