import argparse
import json
from pathlib import Path

from mocap_pose.domain.models import NodePose
from mocap_pose.skeleton.mount_calibration import average_mounting_poses


def main() -> None:
    parser = argparse.ArgumentParser(description="Average a stationary T-pose mounting capture")
    parser.add_argument("input", type=Path, help="JSONL pose.frame.v1 messages")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    frames = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        pose = NodePose(
            int(value["node_id"]),
            int(value["frame_time_us"]),
            tuple(value["quaternion_wxyz"]),
            float(value["quality"]),
            float(value["data_age_ms"]),
            int(value.get("status_flags", 0)),
        )
        frames.append({pose.node_id: pose})
    result = {
        "schema_version": 1,
        "mounting_quaternion_wxyz": {
            str(node): list(quaternion)
            for node, quaternion in average_mounting_poses(frames).items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
