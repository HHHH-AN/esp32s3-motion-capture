"""Fit a saved raw-sensor session; never connect to or silently configure a node."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"host"))
from dashboard.magnetometer import fit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session",type=Path)
    parser.add_argument("--device",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    vectors, boots, sequences = [],set(),set()
    with (args.session/"samples.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            raw=json.loads(line)["data"]["raw"]
            if raw.get("node_id")!=args.device or not raw.get("sensor_flags",0)&2:
                continue
            key=(raw.get("boot_id"),raw.get("sequence"))
            if key in sequences:
                continue
            sequences.add(key);boots.add(raw.get("boot_id"));vectors.append(raw["mag"])
    if len(boots)!=1:
        parser.error("Calibration requires one unchanged device boot session")
    try:
        calibration=fit(vectors)
    except ValueError as exc:
        parser.error(str(exc))
    calibration.update(source_session=args.session.name,source_device_id=args.device)
    from dashboard.magnetometer import validate
    calibration=validate(calibration)
    args.output.write_text(json.dumps(calibration,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(calibration,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
