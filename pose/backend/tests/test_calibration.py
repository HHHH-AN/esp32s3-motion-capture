import math

import numpy as np
import pytest

from mocap_pose.calibration.solver import (
    solve_accelerometer_six_face,
    solve_gyro_bias,
    solve_magnetometer_ellipsoid,
)


def test_gyro_and_six_face_accelerometer_solvers() -> None:
    bias = solve_gyro_bias([(0.01, -0.02, 0.03)] * 20)
    assert bias == pytest.approx((0.01, -0.02, 0.03))
    gravity = 9.80665
    samples = [
        (gravity, 0.0, 0.0),
        (-gravity, 0.0, 0.0),
        (0.0, gravity, 0.0),
        (0.0, -gravity, 0.0),
        (0.0, 0.0, gravity),
        (0.0, 0.0, -gravity),
    ]
    accel_bias, matrix = solve_accelerometer_six_face(samples)
    assert accel_bias == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)
    np.testing.assert_allclose(matrix, np.eye(3), atol=1e-9)


def test_magnetometer_solver_removes_bias_and_axis_scale() -> None:
    hard_iron = np.array((12.0, -8.0, 3.0))
    scales = np.array((2.0, 1.0, 0.5))
    unit_axes = np.vstack((np.eye(3), -np.eye(3)))
    samples = [tuple(hard_iron + axis * scales * 50.0) for axis in unit_axes for _ in range(10)]
    bias, matrix = solve_magnetometer_ellipsoid(samples)
    assert bias == pytest.approx(hard_iron, abs=1e-9)
    corrected_lengths = []
    correction = np.asarray(matrix)
    for sample in samples:
        corrected = correction @ (np.asarray(sample) - np.asarray(bias))
        corrected_lengths.append(float(np.linalg.norm(corrected)))
    assert max(corrected_lengths) - min(corrected_lengths) < 1e-9
    assert math.isfinite(corrected_lengths[0])
