import json
from pathlib import Path

from .schema import SensorCalibration


def save_calibration(path: Path, calibration: SensorCalibration) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(calibration.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_calibration(path: Path) -> SensorCalibration:
    return SensorCalibration.from_dict(json.loads(path.read_text(encoding="utf-8")))

