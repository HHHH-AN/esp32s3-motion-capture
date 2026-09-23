from __future__ import annotations

from dataclasses import dataclass

from mocap_pose.domain.models import CalibratedImuSample, NodePose

from .mahony import MahonyFilter
from .quality import evaluate_sample_quality


@dataclass(slots=True)
class _NodeState:
    filter: MahonyFilter
    previous_timestamp_us: int | None = None


class FusionService:
    def __init__(self, default_dt_s: float = 0.01) -> None:
        self.default_dt_s = default_dt_s
        self._nodes: dict[int, _NodeState] = {}

    def update(self, sample: CalibratedImuSample, frame_time_us: int | None = None) -> NodePose:
        state = self._nodes.setdefault(sample.node_id, _NodeState(MahonyFilter()))
        if state.previous_timestamp_us is None:
            dt_s = self.default_dt_s
        else:
            dt_s = (sample.device_timestamp_us - state.previous_timestamp_us) / 1_000_000
            if not 0 < dt_s <= 0.5:
                dt_s = self.default_dt_s
        state.previous_timestamp_us = sample.device_timestamp_us
        quality, use_magnetometer = evaluate_sample_quality(sample)
        quaternion = state.filter.update(
            sample.gyro_rad_s,
            sample.accel_m_s2,
            sample.mag_ut,
            dt_s,
            use_magnetometer,
        )
        return NodePose(
            node_id=sample.node_id,
            frame_time_us=frame_time_us or sample.device_timestamp_us,
            quaternion_wxyz=quaternion,
            quality=quality,
            data_age_ms=0.0,
            status_flags=sample.status_flags | (0 if use_magnetometer else 0x8000),
        )
