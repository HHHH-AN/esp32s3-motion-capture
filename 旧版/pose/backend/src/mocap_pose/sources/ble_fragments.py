from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field

FRAGMENT_HEADER = struct.Struct("<HBBH")


@dataclass(slots=True)
class _PendingFrame:
    fragment_count: int
    total_length: int
    created_us: int
    fragments: dict[int, bytes] = field(default_factory=dict)


class BleFragmentReassembler:
    """Strictly reassembles the six-byte BLE fragment contract into one COBS frame."""

    def __init__(self, timeout_us: int = 1_000_000, maximum_frame_length: int = 4096) -> None:
        self.timeout_us = timeout_us
        self.maximum_frame_length = maximum_frame_length
        self._pending: dict[int, _PendingFrame] = {}
        self.completed_frames = 0
        self.invalid_frames = 0
        self.duplicate_frames = 0
        self.timed_out_frames = 0

    def _expire(self, now_us: int) -> None:
        expired = [
            frame_id
            for frame_id, state in self._pending.items()
            if now_us - state.created_us > self.timeout_us
        ]
        for frame_id in expired:
            del self._pending[frame_id]
            self.timed_out_frames += 1

    def push(self, notification: bytes, now_us: int | None = None) -> bytes | None:
        now_us = now_us if now_us is not None else time.monotonic_ns() // 1000
        self._expire(now_us)
        if len(notification) < FRAGMENT_HEADER.size:
            self.invalid_frames += 1
            return None
        frame_id, index, count, total_length = FRAGMENT_HEADER.unpack_from(notification)
        payload = notification[FRAGMENT_HEADER.size :]
        if (
            count == 0
            or index >= count
            or total_length == 0
            or total_length > self.maximum_frame_length
            or not payload
            or len(payload) > total_length
        ):
            self._pending.pop(frame_id, None)
            self.invalid_frames += 1
            return None
        state = self._pending.get(frame_id)
        if state is None:
            state = _PendingFrame(count, total_length, now_us)
            self._pending[frame_id] = state
        elif state.fragment_count != count or state.total_length != total_length:
            del self._pending[frame_id]
            self.invalid_frames += 1
            return None
        if index in state.fragments:
            del self._pending[frame_id]
            self.duplicate_frames += 1
            return None
        state.fragments[index] = payload
        if len(state.fragments) != count:
            return None
        del self._pending[frame_id]
        try:
            assembled = b"".join(state.fragments[item] for item in range(count))
        except KeyError:
            self.invalid_frames += 1
            return None
        if len(assembled) != total_length:
            self.invalid_frames += 1
            return None
        self.completed_frames += 1
        return assembled

