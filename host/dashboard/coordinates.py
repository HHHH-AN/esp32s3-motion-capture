"""Signed sensor-axis permutations; attitude fusion always uses a right-handed frame."""
from dataclasses import dataclass, replace

from .models import SensorSample


@dataclass(frozen=True)
class CoordinateSettings:
    sensor_axes: tuple[str, str, str] = ("+X", "+Y", "+Z")
    displacement_signs: tuple[int, int, int] = (1, 1, 1)

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError("坐标设置必须是对象")
        axes = data.get("sensor_axes", ["+X", "+Y", "+Z"])
        signs = data.get("displacement_signs", [1, 1, 1])
        if not isinstance(axes, (list, tuple)) or len(axes) != 3 or any(a not in ("+X", "-X", "+Y", "-Y", "+Z", "-Z") for a in axes):
            raise ValueError("每个输出轴需选择 +X/-X/+Y/-Y/+Z/-Z")
        indices = ["XYZ".index(a[1]) for a in axes]
        if len(set(indices)) != 3:
            raise ValueError("X、Y、Z 原始轴必须各使用一次")
        inversions = sum(indices[i] > indices[j] for i in range(3) for j in range(i+1, 3))
        determinant = (-1)**inversions * (-1)**sum(a[0] == "-" for a in axes)
        if determinant != 1:
            raise ValueError("传感器映射需保持右手系：同时翻转两轴，或交换两轴并翻转一轴；位移显示方向可单独翻转")
        if not isinstance(signs, (list, tuple)) or len(signs) != 3 or any(type(s) is not int or s not in (-1, 1) for s in signs):
            raise ValueError("位移方向需为 +1 或 -1")
        return cls(tuple(axes), tuple(signs))

    def sensor_vector(self, vector):
        return tuple(vector["XYZ".index(a[1])] * (1 if a[0] == "+" else -1) for a in self.sensor_axes)

    def sample(self, sample: SensorSample) -> SensorSample:
        return replace(sample, accel=self.sensor_vector(sample.accel),
                       gyro=self.sensor_vector(sample.gyro), mag=self.sensor_vector(sample.mag))

    def display_vector(self, vector):
        return tuple(v*s for v, s in zip(vector, self.displacement_signs))

    def payload(self):
        return {"sensor_axes": self.sensor_axes, "displacement_signs": self.displacement_signs}
