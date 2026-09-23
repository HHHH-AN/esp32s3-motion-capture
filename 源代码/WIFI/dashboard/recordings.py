from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path


CSV_FILES = ("imu-data.csv", "body-trajectory.csv", "node-trajectory.csv")


class RecordingNotFound(ValueError):
    pass


def recording_root(root: Path | None = None) -> Path:
    return (root or Path("recordings")).resolve()


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
        for name in CSV_FILES:
            path = folder / name
            if path.is_file():
                archive.write(path, arcname=f"{session}/{name}")
    return output.getvalue()
