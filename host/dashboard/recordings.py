from __future__ import annotations

import csv
import io
import math
import json
from .coordinates import CoordinateSettings
import zipfile
from pathlib import Path


CSV_FILES = ("imu-data.csv", "body-trajectory.csv", "node-trajectory.csv")
EXPORT_FILES = (*CSV_FILES, "metadata.json")


class RecordingNotFound(ValueError):
    pass


def recording_root(root: Path | None = None) -> Path:
    return (root or Path(__file__).resolve().parent.parent / "recordings").resolve()


def safe_item(name: str, root: Path | None = None) -> Path:
    base = recording_root(root)
    candidate = (base / name).resolve()
    if candidate.parent != base or not candidate.exists():
        raise RecordingNotFound(name)
    return candidate


def catalog(root: Path | None = None) -> list[dict]:
    base = recording_root(root)
    if not base.exists():
        return []
    result = []
    for item in sorted(base.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
        if item.is_dir():
            files = []
            for name in CSV_FILES:
                path = item / name
                if path.is_file():
                    files.append({"name": name, "size": path.stat().st_size})
            result.append({"id": item.name, "kind": "csv_session", "modified": item.stat().st_mtime, "files": files})
        elif item.suffix.lower() == ".jsonl":
            result.append({"id": item.name, "kind": "legacy_jsonl", "modified": item.stat().st_mtime,
                           "files": [{"name": item.name, "size": item.stat().st_size}]})
    return result


def preview_csv(session: str, filename: str, limit: int = 100, root: Path | None = None) -> dict:
    folder = safe_item(session, root)
    if not folder.is_dir() or filename not in CSV_FILES:
        raise RecordingNotFound(filename)
    path = (folder / filename).resolve()
    if path.parent != folder or not path.is_file():
        raise RecordingNotFound(filename)
    rows, total, first_time, last_time = [], 0, None, None
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        for row in reader:
            total += 1
            if row:
                first_time = first_time or row[0]
                last_time = row[0]
            if len(rows) < max(1, min(limit, 200)):
                rows.append(row)
    return {"session": session, "file": filename, "header": header, "rows": rows,
            "total_rows": total, "first_timestamp": first_time, "last_timestamp": last_time,
            "size": path.stat().st_size}


def session_zip(session: str, root: Path | None = None) -> bytes:
    folder = safe_item(session, root)
    if not folder.is_dir():
        raise RecordingNotFound(session)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in EXPORT_FILES:
            path = (folder / name).resolve()
            if path.parent == folder and path.is_file():
                archive.write(path, arcname=f"{session}/{name}")
    return output.getvalue()


def replay_data(session: str, root: Path | None = None) -> dict:
    """Return at most 5000 evenly spaced samples; the CSV export remains complete."""
    folder = safe_item(session, root)
    path = (folder / "imu-data.csv").resolve()
    if not folder.is_dir() or path.parent != folder or not path.is_file():
        raise RecordingNotFound(session)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        count = sum(1 for _ in csv.DictReader(handle))
    stride = max(1, math.ceil(count / 4999))
    axis_signs = (1,1,1)
    metadata = (folder / "metadata.json").resolve()
    if metadata.parent == folder and metadata.is_file():
        try:
            settings = json.loads(metadata.read_text(encoding="utf-8")).get("coordinates",{})
            axis_signs = CoordinateSettings.parse(settings).displacement_signs
        except (ValueError,TypeError,OSError):
            pass
    frames, peak, first, last = [], 0.0, None, None
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            try:
                timestamp = float(row["时间戳"])
                q = [float(row[f"四元数{k}"]) for k in "WXYZ"]
                acc = [float(row[f"加速度{k}"]) for k in "XYZ"]
                gyro = [float(row[f"角速度{k}"]) for k in "XYZ"]
                mag = [float(row[f"磁场{k}"]) for k in "XYZ"]
                if not all(math.isfinite(v) for v in [timestamp, *q, *acc, *gyro, *mag]):
                    continue
                peak = max(peak, math.sqrt(sum(v*v for v in gyro)))
                first = timestamp if first is None else first
                last = timestamp
                if index % stride == 0 or index == count - 1:
                    motion = None
                    if "位移X米" in row:
                        position = [float(row[f"位移{k}米"]) for k in "XYZ"]
                        velocity = [float(row[f"速度{k}米每秒"]) for k in "XYZ"]
                        linear_accel = [float(row[f"线性加速度{k}米每秒平方"]) for k in "XYZ"]
                        motion = {"position":position,"velocity":velocity,"linear_accel":linear_accel,
                                  "phase":row["位移估算阶段"],"elapsed_s":float(row["位移估算秒"]),
                                  "distance":math.sqrt(sum(v*v for v in position)),
                                  "speed":math.sqrt(sum(v*v for v in velocity)),"message":"已记录的位移估算（未经定位验证）"}
                        if "静止修正启用" in row:
                            motion.update({"zupt":row["静止修正启用"]=="1",
                                           "stationary":row["静止检测确认"]=="1",
                                           "zupt_count":int(row["速度归零次数"])})
                            motion["quality"] = ("inactive" if motion["phase"] != "measuring" else
                                                 "stationary_constraint" if motion["zupt"] and motion["stationary"] else "inertial_only")
                    frames.append({"timestamp": timestamp, "node_id": row["节点ID"],
                                   "quaternion": q, "accel": acc, "gyro": gyro, "mag": mag,"motion":motion,
                                   "axis_signs":axis_signs})
            except (ValueError, KeyError):
                continue
    return {"frames": frames, "total_rows": count, "stride": stride,
            "duration_s": max(0, last-first) if first is not None else 0,
            "peak_gyro_dps": peak}
