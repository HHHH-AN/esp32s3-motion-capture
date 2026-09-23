import argparse
import json
from pathlib import Path

from mocap_pose.calibration.schema import SensorCalibration
from mocap_pose.calibration.solver import (
    solve_accelerometer_six_face,
    solve_gyro_bias,
    solve_magnetometer_ellipsoid,
)
from mocap_pose.calibration.store import save_calibration


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solve sensor calibration from prepared XYZ captures"
    )
    parser.add_argument(
        "input", type=Path, help="JSON with gyro_rad_s, accel_m_s2 and mag_ut arrays"
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--device-uid", required=True)
    args = parser.parse_args()
    values = json.loads(args.input.read_text(encoding="utf-8"))
    accel_bias, accel_matrix = solve_accelerometer_six_face(values["accel_m_s2"])
    mag_bias, mag_matrix = solve_magnetometer_ellipsoid(values["mag_ut"])
    calibration = SensorCalibration(
        args.device_uid,
        gyro_bias_rad_s=solve_gyro_bias(values["gyro_rad_s"]),
        accel_bias_m_s2=accel_bias,
        accel_matrix=accel_matrix,
        mag_bias_ut=mag_bias,
        mag_matrix=mag_matrix,
    )
    save_calibration(args.output, calibration)
    print(args.output)


if __name__ == "__main__":
    main()
