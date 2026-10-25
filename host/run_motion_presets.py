"""Run offline demos, replay raw data, or explicitly capture three TCP nodes."""
from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
from uuid import uuid4

from motion_presets.engine import ExperimentError, analyse
from motion_presets.report import write_report
from motion_presets.sources import RAW_FIELDS, capture_tcp, demo_rows, read_raw


ROOT = Path(__file__).resolve().parent
PRESETS = ("rigid_check", "upper_limb", "lower_limb", "bilateral")


def load_settings(preset_id, endpoint_file=None):
    preset = json.loads((ROOT / "presets" / f"{preset_id}.json").read_text(encoding="utf-8"))
    coordinate = json.loads((ROOT / "coordinate_settings.json").read_text(encoding="utf-8"))
    axes = [list(coordinate["sensor_axes"]) for _ in range(3)]
    endpoints = None
    if endpoint_file:
        settings = json.loads(Path(endpoint_file).read_text(encoding="utf-8"))
        nodes = settings["nodes"]
        if set(nodes) != {"A", "B", "C"}:
            raise ExperimentError("端点配置必须恰好包含 A、B、C")
        endpoints = []
        for index, slot in enumerate(("A", "B", "C")):
            node = nodes[slot]
            host, port = node.get("host"), node.get("port", 9000)
            if not isinstance(host, str) or not host.strip() or host != host.strip() or any(c.isspace() for c in host):
                raise ExperimentError(f"请在端点配置中填写节点 {slot} 的真实 IP/主机名")
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ExperimentError("TCP 端口需为 1..65535 的整数")
            endpoints.append((host, port))
            axes[index] = node.get("sensor_axes", axes[index])
        if len(set(endpoints)) != 3:
            raise ExperimentError("三个 TCP 端点必须不同，不能将同一块板子当作三个节点")
    return preset, axes, endpoints


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=PRESETS, default="upper_limb")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="Synthetic data; default mode; no network")
    source.add_argument("--live", action="store_true", help="Explicitly connect to three configured TCP hosts")
    source.add_argument("--replay", type=Path, help="Reanalyse a raw.csv recorded by this tool")
    parser.add_argument("--endpoints", type=Path, help="JSON with nodes A/B/C; required for --live")
    parser.add_argument("--duration", type=float, default=20, help="Total capture seconds including initial static calibration (8..120)")
    parser.add_argument("--output", type=Path, help="New output directory; existing directories are never overwritten")
    args = parser.parse_args(argv)
    if not 8 <= args.duration <= 120:
        parser.error("duration must be 8..120 seconds; use short trials without proven clock synchronisation")
    if args.live and not args.endpoints:
        parser.error("--live requires --endpoints presets/endpoints.local.json")
    folder = args.output or ROOT / "preset_runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{args.preset}-{uuid4().hex[:6]}"
    created = False
    try:
        preset, axes, endpoints = load_settings(args.preset, args.endpoints)
        source_kind = "live_tcp" if args.live else "replay" if args.replay else "synthetic_demo"
        # Keep a replay self-contained: original axes/source must not be silently
        # replaced by today's coordinate settings or relabelled as real data.
        if args.replay:
            previous = args.replay.parent / "session.json"
            if not previous.exists():
                raise ExperimentError("回放缺少同目录 session.json，无法确认来源和坐标映射")
            original = json.loads(previous.read_text(encoding="utf-8"))
            if original["preset_id"] != args.preset:
                raise ExperimentError("回放预设与采集预设不一致，请使用 session.json 中的 preset_id")
            preset = original["preset"]
            axes = original["sensor_axes"]
            original_kind = original.get("original_source_kind", original["source_kind"])
        else:
            original_kind = source_kind
        # Validate axis mappings before any network activity.
        from dashboard.coordinates import CoordinateSettings
        for mapping in axes:
            CoordinateSettings.parse({"sensor_axes": mapping})
        folder.mkdir(parents=True, exist_ok=False)
        created = True
        session = {"schema_version": 1, "preset_id": args.preset, "source_kind": source_kind,
                   "original_source_kind": original_kind, "sensor_axes": axes, "preset": preset,
                   "endpoints": endpoints, "duration_requested_s": args.duration}
        (folder / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        with (folder / "raw.csv").open("w", encoding="utf-8-sig", newline="") as raw:
            writer = csv.DictWriter(raw, fieldnames=RAW_FIELDS)
            writer.writeheader()
            if args.live:
                rows = asyncio.run(capture_tcp(endpoints, args.duration, writer))
            else:
                rows = read_raw(args.replay) if args.replay else list(demo_rows(preset, args.duration, axes))
                writer.writerows(rows)
        result = analyse(preset, rows, axes)
        result.update({"source_kind": source_kind, "original_source_kind": original_kind,
                       "validation_status": "software_demo_only" if original_kind == "synthetic_demo" else "unvalidated_sensor_measurements"})
        with (folder / "aligned.csv").open("w", encoding="utf-8-sig", newline="") as output:
            angle_keys = list(preset["angle_labels"])
            writer = csv.writer(output)
            writer.writerow(["time_s", "valid", *angle_keys, "gyro_A_dps", "gyro_B_dps", "gyro_C_dps",
                             *(f"q_{slot}_{axis}" for slot in ("A", "B", "C") for axis in "wxyz")])
            for frame in result["frames"]:
                writer.writerow([frame["t"], int(frame["valid"]), *(frame["angles"].get(k, "") for k in angle_keys),
                                 *(frame["speeds"] if frame["valid"] else [""]*3),
                                 *(v for q in frame.get("quaternions", [[""]*4]*3) for v in q)])
        summary = {key: value for key, value in result.items() if key != "frames"}
        (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        write_report(folder / "report.html", preset, result)
        print(f"Preset: {preset['title']}")
        print(f"Source: {original_kind}; no inertial position integration")
        print(f"Valid aligned frames: {result['valid_aligned_frames']}")
        for key, value in result["metrics"].items():
            print(f"  {key}: range={value['range_deg']:.2f} deg, max={value['max_deg']:.2f} deg")
        for key, value in result["repetitions"].items():
            print(f"  {key}: completed cycles={value['count']}")
        print(f"Report: {(folder / 'report.html').resolve()}")
        return 0
    except (ExperimentError, ValueError, KeyError, OSError, asyncio.LimitOverrunError) as exc:
        print(f"Experiment stopped: {exc}", file=sys.stderr)
        if created:
            (folder / "error.json").write_text(json.dumps({"error": str(exc), "complete": False}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Partial data: {folder.resolve()}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; any partial raw.csv is retained. No result was declared successful.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
