import math

from mocap_pose.domain.models import CalibratedImuSample

STANDARD_GRAVITY = 9.80665
MAG_MIN_UT = 15.0
MAG_MAX_UT = 100.0


def evaluate_sample_quality(sample: CalibratedImuSample) -> tuple[float, bool]:
    accel_norm = math.sqrt(sum(value * value for value in sample.accel_m_s2))
    mag_norm = math.sqrt(sum(value * value for value in sample.mag_ut))
    accel_score = max(0.0, 1.0 - abs(accel_norm - STANDARD_GRAVITY) / STANDARD_GRAVITY)
    magnetometer_valid = MAG_MIN_UT <= mag_norm <= MAG_MAX_UT and sample.mag_age_us <= 50_000
    mag_score = 1.0 if magnetometer_valid else 0.45
    return min(1.0, 0.65 * accel_score + 0.35 * mag_score), magnetometer_valid

