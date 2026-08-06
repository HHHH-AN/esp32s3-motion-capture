from __future__ import annotations

import datetime as dt
from pathlib import Path

from mocap_pose.domain.models import IngressPacket
from mocap_pose.protocol.decoder import StreamDecoder
from mocap_pose.storage.raw_session import RawSessionWriter


class RecordingController:
    def __init__(self, root: Path, expected_nodes: tuple[int, ...]) -> None:
        self.root = root
        self.expected_nodes = expected_nodes
        self.writer: RawSessionWriter | None = None
        self.decoder = StreamDecoder()
        self.last_session: Path | None = None

    def start(self) -> Path:
        if self.writer is not None:
            raise RuntimeError("recording is already active")
        self.decoder = StreamDecoder()
        now = dt.datetime.now()
        session = self.root / now.strftime("session_%Y%m%d_%H%M%S_%f")
        self.writer = RawSessionWriter(
            session,
            {
                "protocol_version": 1,
                "firmware_version": "reported-per-device-or-unknown",
                "config_version": "human-14-v1",
                "nodes": list(self.expected_nodes),
                "created_at": now.isoformat(),
            },
        )
        self.last_session = session
        return session

    def observe(self, packet: IngressPacket) -> None:
        if self.writer is None:
            return
        frames = self.decoder.feed(packet.data)
        node_ids = ";".join(str(frame.node_id) for frame in frames)
        sequences = ";".join(str(frame.sequence) for frame in frames)
        self.writer.write(packet, node_ids, sequences)

    def stop(self) -> Path:
        if self.writer is None or self.last_session is None:
            raise RuntimeError("recording is not active")
        self.writer.close()
        self.writer = None
        return self.last_session

    @property
    def active(self) -> bool:
        return self.writer is not None
