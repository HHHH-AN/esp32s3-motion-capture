from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from mocap_pose.domain.models import RawImuSample


@dataclass(frozen=True, slots=True)
class RawQualityReport:
    sample_count: int
    mean_accel_g: float
    accel_std_g: float
    mean_interval_ms: float | None
    max_interval_ms: float | None
    sequence_gaps: int


def analyze_raw_samples(samples: Sequence[RawImuSample]) -> RawQualityReport:
    if not samples:
        raise ValueError("at least one sample is required")
    magnitudes = [
        math.sqrt(sum(axis * axis for axis in sample.accel_mg)) / 1000
        for sample in samples
    ]
    intervals = [
        (current.device_timestamp_us - previous.device_timestamp_us) / 1000
        for previous, current in zip(samples, samples[1:], strict=False)
        if current.device_timestamp_us >= previous.device_timestamp_us
    ]
    gaps = sum(
        max(0, ((current.sequence - previous.sequence) & 0xFFFFFFFF) - 1)
        for previous, current in zip(samples, samples[1:], strict=False)
    )
    return RawQualityReport(
        len(samples),
        statistics.fmean(magnitudes),
        statistics.pstdev(magnitudes),
        statistics.fmean(intervals) if intervals else None,
        max(intervals) if intervals else None,
        gaps,
    )
