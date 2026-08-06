from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from mocap_pose.domain.models import IngressPacket


class RawSessionWriter:
    REQUIRED_METADATA = {
        "protocol_version",
        "firmware_version",
        "config_version",
        "nodes",
    }

    def __init__(self, path: Path, metadata: dict[str, Any]) -> None:
        missing = self.REQUIRED_METADATA - metadata.keys()
        if missing:
            raise ValueError(f"recording metadata is missing: {', '.join(sorted(missing))}")
        self.path = path
        path.mkdir(parents=True, exist_ok=False)
        (path / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._packets = (path / "packets.bin").open("wb")
        self._index_file = (path / "index.csv").open("w", newline="", encoding="utf-8")
        self._index = csv.writer(self._index_file)
        self._index.writerow(
            ("offset", "length", "arrival_time_us", "transport", "node_id", "sequence")
        )
        self._offset = 0
        self._closed = False

    def write(
        self,
        packet: IngressPacket,
        node_id: str | int = "",
        sequence: str | int = "",
    ) -> None:
        if self._closed:
            raise RuntimeError("session is closed")
        self._packets.write(packet.data)
        self._index.writerow(
            (
                self._offset,
                len(packet.data),
                packet.arrival_time_us,
                packet.transport,
                node_id,
                sequence,
            )
        )
        self._offset += len(packet.data)

    def close(self) -> None:
        if not self._closed:
            self._packets.close()
            self._index_file.close()
            self._closed = True

    def __enter__(self) -> RawSessionWriter:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class RawSessionReader:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def metadata(self) -> dict[str, Any]:
        return json.loads((self.path / "metadata.json").read_text(encoding="utf-8"))

    def packets(self):
        with (self.path / "packets.bin").open("rb") as packets_file, (
            self.path / "index.csv"
        ).open(newline="", encoding="utf-8") as index_file:
            for row in csv.DictReader(index_file):
                offset, length = int(row["offset"]), int(row["length"])
                packets_file.seek(offset)
                data = packets_file.read(length)
                if len(data) != length:
                    raise ValueError("recording index points outside packets.bin")
                yield IngressPacket(data, int(row["arrival_time_us"]), row["transport"])
