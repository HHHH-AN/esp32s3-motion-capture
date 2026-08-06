from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from mocap_pose.domain.models import Vector3

from .apply import STANDARD_GRAVITY
from .schema import Matrix3


def _require_samples(samples: Sequence[Vector3], minimum: int) -> np.ndarray:
    if len(samples) < minimum:
        raise ValueError(f"at least {minimum} samples are required")
    values = np.asarray(samples, dtype=float)
    if values.shape != (len(samples), 3) or not np.isfinite(values).all():
        raise ValueError("samples must contain finite XYZ vectors")
    return values


def solve_gyro_bias(samples_rad_s: Sequence[Vector3]) -> Vector3:
    values = _require_samples(samples_rad_s, 10)
    return tuple(float(value) for value in values.mean(axis=0))  # type: ignore[return-value]


def solve_accelerometer_six_face(
    samples_m_s2: Sequence[Vector3], gravity: float = STANDARD_GRAVITY
) -> tuple[Vector3, Matrix3]:
    values = _require_samples(samples_m_s2, 6)
    minimum, maximum = values.min(axis=0), values.max(axis=0)
    span = maximum - minimum
    if np.any(span < gravity):
        raise ValueError("six-face capture does not cover both directions of every axis")
    bias = (maximum + minimum) / 2
    scale = (2 * gravity) / span
    matrix = np.diag(scale)
    return (
        tuple(float(value) for value in bias),  # type: ignore[return-value]
        tuple(tuple(float(value) for value in row) for row in matrix),  # type: ignore[return-value]
    )


def solve_magnetometer_ellipsoid(samples_ut: Sequence[Vector3]) -> tuple[Vector3, Matrix3]:
    """Estimate hard-iron bias and a symmetric covariance-whitening soft-iron matrix."""
    values = _require_samples(samples_ut, 60)
    minimum, maximum = values.min(axis=0), values.max(axis=0)
    bias = (maximum + minimum) / 2
    centered = values - bias
    covariance = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    if np.any(eigenvalues <= 1e-9):
        raise ValueError("magnetometer capture does not span three dimensions")
    target_variance = float(np.exp(np.log(eigenvalues).mean()))
    correction = eigenvectors @ np.diag(np.sqrt(target_variance / eigenvalues)) @ eigenvectors.T
    corrected_norms = np.linalg.norm(centered @ correction.T, axis=1)
    if not math.isfinite(float(corrected_norms.mean())):
        raise ValueError("invalid magnetometer solution")
    return (
        tuple(float(value) for value in bias),  # type: ignore[return-value]
        tuple(tuple(float(value) for value in row) for row in correction),  # type: ignore[return-value]
    )

