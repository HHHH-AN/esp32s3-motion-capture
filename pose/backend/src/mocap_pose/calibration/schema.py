from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mocap_pose.domain.models import Vector3

Matrix3 = tuple[Vector3, Vector3, Vector3]
IDENTITY_MATRIX: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@dataclass(frozen=True, slots=True)
class SensorCalibration:
    device_uid: str
    version: int = 1
    gyro_bias_rad_s: Vector3 = (0.0, 0.0, 0.0)
    accel_bias_m_s2: Vector3 = (0.0, 0.0, 0.0)
    accel_matrix: Matrix3 = IDENTITY_MATRIX
    mag_bias_ut: Vector3 = (0.0, 0.0, 0.0)
    mag_matrix: Matrix3 = IDENTITY_MATRIX

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SensorCalibration:
        def vec3(name: str) -> Vector3:
            raw = value[name]
            return float(raw[0]), float(raw[1]), float(raw[2])

        def matrix3(name: str) -> Matrix3:
            raw = value[name]
            return tuple(tuple(float(item) for item in row) for row in raw)  # type: ignore[return-value]

        version = int(value.get("version", 0))
        if version != 1:
            raise ValueError(f"unsupported calibration version {version}")
        return cls(
            device_uid=str(value["device_uid"]),
            version=version,
            gyro_bias_rad_s=vec3("gyro_bias_rad_s"),
            accel_bias_m_s2=vec3("accel_bias_m_s2"),
            accel_matrix=matrix3("accel_matrix"),
            mag_bias_ut=vec3("mag_bias_ut"),
            mag_matrix=matrix3("mag_matrix"),
        )

