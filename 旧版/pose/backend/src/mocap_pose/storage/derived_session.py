from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonLinesSession:
    """Writes derived pose/skeleton messages with provenance in a sidecar file."""

    def __init__(self, path: Path, provenance: dict[str, Any]) -> None:
        path.mkdir(parents=True, exist_ok=False)
        (path / "provenance.json").write_text(
            json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._stream = (path / "frames.jsonl").open("w", encoding="utf-8")

    def write(self, message: dict[str, Any]) -> None:
        self._stream.write(json.dumps(message, separators=(",", ":")) + "\n")

    def close(self) -> None:
        self._stream.close()

