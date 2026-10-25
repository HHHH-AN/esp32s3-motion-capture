"""Package the current source and reviewed evidence, omitting local settings.

Run from any directory. The output ZIP must be a new file inside this repository;
no working files are changed. Known Wi-Fi passwords are scrubbed from text copies
and checked before and after writing the archive.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = {"firmware", "host", "tools", "docs", ".github"}
SOURCE_FILES = {"README.md", "AGENTS.md", ".gitignore", ".gitattributes",
                "LICENSE", "LICENSE.md", "THIRD_PARTY_NOTICES.md"}
TEXT_SUFFIXES = {".py", ".js", ".html", ".css", ".md", ".h", ".hpp", ".c", ".cpp",
                 ".ini", ".json", ".csv", ".txt", ".ps1", ".toml", ".yaml", ".yml", ".svg"}
SKIP_DIRS = {".git", ".codex", ".pio", ".platformio", ".pio-core", ".venv", "venv",
             "__pycache__", ".vscode", ".idea", ".pytest_cache", ".mypy_cache", ".ruff_cache",
             "node_modules", "recordings", "preset_runs", "hardware_tests", "logs", "build",
             "dist", "exports", "secrets", "credentials"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".bin", ".elf", ".map", ".o", ".a", ".log", ".zip",
                 ".7z", ".pem", ".key", ".p12", ".pfx"}


def reparse(path: Path) -> bool:
    attributes = path.lstat().st_file_attributes if os.name == "nt" else 0
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def excluded(relative: Path) -> bool:
    return (any(part in SKIP_DIRS or part.startswith("before_") for part in relative.parts)
            or relative.name == "wifi_config.h" or relative.name.startswith(".env")
            or relative.name.endswith(".local.json") or relative.suffix.lower() in SKIP_SUFFIXES)


def source_files():
    for name in sorted(SOURCE_FILES):
        source = ROOT / name
        if source.is_file() and not source.is_symlink() and not reparse(source):
            yield source
    for name in sorted(SOURCE_DIRS):
        directory = ROOT / name
        if not directory.is_dir() or directory.is_symlink() or reparse(directory):
            continue
        for current, directories, files in os.walk(directory, followlinks=False):
            current = Path(current)
            directories[:] = sorted(child for child in directories
                if not excluded((current / child).relative_to(ROOT))
                and not (current / child).is_symlink() and not reparse(current / child))
            for child in sorted(files):
                source = current / child
                if (source.is_file() and not source.is_symlink() and not reparse(source)
                        and not excluded(source.relative_to(ROOT))):
                    yield source


def passwords():
    private = ROOT / "firmware" / "include" / "wifi_config.h"
    if not private.is_file():
        return []
    try:
        contents = private.read_text(encoding="utf-8-sig")
        literals = re.findall(r'^\s*#define\s+(?:WIFI_PASSWORD|WIFI_AP_PASSWORD)\s+("(?:\\.|[^"\\])*")', contents, re.M)
        values = {json.loads(value) for value in literals}
        return sorted((value for value in values if value), key=len, reverse=True)
    except (OSError, ValueError):
        raise ValueError("Could not inspect the private Wi-Fi configuration; packaging stopped without printing its contents") from None


def scrub(data, suffix, secrets):
    if suffix not in TEXT_SUFFIXES and suffix:
        return data
    try:
        value = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data
    changed = value
    for secret in secrets:
        changed = changed.replace(secret, "[private password removed]")
    return changed.encode("utf-8") if changed != value else data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New ZIP path inside this repository, e.g. exports/imu-source.zip")
    parser.add_argument("--date", required=True, help="User-facing date in YYYY-MM-DD format")
    args = parser.parse_args()
    try:
        stamp = date.fromisoformat(args.date)
        if stamp.isoformat() != args.date:
            raise ValueError
    except ValueError:
        parser.error("date must be a valid YYYY-MM-DD date")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.suffix.lower() != ".zip":
        parser.error("output must be a ZIP inside this repository")
    if output.exists():
        parser.error("output already exists; choose another name")
    if not (ROOT / "firmware" / "platformio.ini").is_file() or not (ROOT / "host" / "run_dashboard.py").is_file():
        parser.error("expected firmware/platformio.ini and host/run_dashboard.py in this repository")

    secrets = passwords()
    entries = {source.relative_to(ROOT).as_posix(): scrub(source.read_bytes(), source.suffix.lower(), secrets)
               for source in source_files()}
    evidence_count = sum(name.startswith("docs/validation/evidence/") for name in entries)
    info = {"date": args.date, "source_layout": "firmware + host (including tests) + tools + docs",
            "reviewed_evidence_files": evidence_count, "private_config_included": False,
            "personal_runtime_data_included": False, "firmware_binaries_included": False,
            "known_wifi_passwords_scrubbed_from_text": bool(secrets), "source_tree_modified_by_packaging": False}
    entries["PACKAGE_INFO.json"] = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    for name, data in entries.items():
        if any(secret.encode("utf-8") in data for secret in secrets):
            raise ValueError("Known Wi-Fi credential remains in entry (contents suppressed): " + name)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    entries["SHA256SUMS"] = "".join(hashes[name] + "  " + name + "\n" for name in sorted(hashes)).encode("utf-8")
    top = "esp32s3-motion-capture-" + stamp.strftime("%Y%m%d")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            archive.writestr(top + "/" + name, entries[name])
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != {top + "/" + name for name in entries}:
            raise ValueError("ZIP integrity check failed")
        for name, digest in hashes.items():
            data = archive.read(top + "/" + name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("Manifest hash mismatch: " + name)
            if any(secret.encode("utf-8") in data for secret in secrets):
                raise ValueError("Known credential found in archive entry (contents suppressed): " + name)
    print(json.dumps({"zip": str(output), "files": len(entries), "evidence_files": evidence_count,
                      "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "integrity_checked": True, "known_wifi_password_scan_passed": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
