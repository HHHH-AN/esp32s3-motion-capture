import math

from mocap_pose.domain.models import CalibratedImuSample, RawImuSample, Vector3

from .schema import Matrix3, SensorCalibration

STANDARD_GRAVITY = 9.80665


def _subtract(vector: Vector3, bias: Vector3) -> Vector3:
    return tuple(
        value - offset for value, offset in zip(vector, bias, strict=True)
    )  # type: ignore[return-value]


def _matvec(matrix: Matrix3, vector: Vector3) -> Vector3:
    return tuple(sum(row[index] * vector[index] for index in range(3)) for row in matrix)  # type: ignore[return-value]


def apply_calibration(
    sample: RawImuSample, calibration: SensorCalibration | None = None
) -> CalibratedImuSample:
    calibration = calibration or SensorCalibration(device_uid=f"node-{sample.node_id}")
    accel_raw: Vector3 = tuple(
        value * STANDARD_GRAVITY / 1000 for value in sample.accel_mg
    )  # type: ignore[assignment]
    gyro_raw: Vector3 = tuple(
        math.radians(value / 10) for value in sample.gyro_dps_x10
    )  # type: ignore[assignment]
    mag_raw: Vector3 = tuple(value / 10 for value in sample.mag_ut_x10)  # type: ignore[assignment]
    return CalibratedImuSample(
        node_id=sample.node_id,
        sequence=sample.sequence,
        device_timestamp_us=sample.device_timestamp_us,
        accel_m_s2=_matvec(
            calibration.accel_matrix, _subtract(accel_raw, calibration.accel_bias_m_s2)
        ),
        gyro_rad_s=_subtract(gyro_raw, calibration.gyro_bias_rad_s),
        mag_ut=_matvec(calibration.mag_matrix, _subtract(mag_raw, calibration.mag_bias_ut)),
        temperature_c=sample.temperature_c_x100 / 100,
        mag_age_us=sample.mag_age_us,
        status_flags=sample.status_flags,
    )
