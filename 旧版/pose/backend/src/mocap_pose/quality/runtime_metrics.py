from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(slots=True)
class RuntimeMetrics:
    started_us: int = field(default_factory=lambda: time.monotonic_ns() // 1000)
    packets: int = 0
    bytes_received: int = 0
    decoded_frames: int = 0
    rejected_frames: int = 0
    sequence_gaps: int = 0
    queue_drops: int = 0
    last_sequence: dict[int, int] = field(default_factory=dict)
    per_node_packets: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def on_packet(self, size: int) -> None:
        self.packets += 1
        self.bytes_received += size

    def on_frame(self, node_id: int, sequence: int) -> None:
        self.decoded_frames += 1
        self.per_node_packets[node_id] += 1
        previous = self.last_sequence.get(node_id)
        if previous is not None:
            self.sequence_gaps += max(0, ((sequence - previous) & 0xFFFFFFFF) - 1)
        self.last_sequence[node_id] = sequence

    def snapshot(self) -> dict[str, object]:
        elapsed_s = max((time.monotonic_ns() // 1000 - self.started_us) / 1_000_000, 1e-9)
        return {
            "uptime_s": elapsed_s,
            "packets": self.packets,
            "bytes_received": self.bytes_received,
            "decoded_frames": self.decoded_frames,
            "rejected_frames": self.rejected_frames,
            "sequence_gaps": self.sequence_gaps,
            "queue_drops": self.queue_drops,
            "frames_per_second": self.decoded_frames / elapsed_s,
            "per_node_packets": dict(self.per_node_packets),
        }
