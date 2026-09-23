from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

from mocap_pose.domain.models import IngressPacket
from mocap_pose.storage.raw_session import RawSessionReader

from .base import PacketSource


class ReplaySource(PacketSource):
    def __init__(self, session_path: Path, speed: float = 1.0, loop: bool = False) -> None:
        if speed <= 0:
            raise ValueError("replay speed must be positive")
        self.session_path = session_path
        self.speed = speed
        self.loop = loop
        self._running = False
        self._resume_event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        self._resume_event.set()

    async def stop(self) -> None:
        self._running = False
        self._resume_event.set()

    def pause(self) -> None:
        self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("replay speed must be positive")
        self.speed = speed

    async def packets(self) -> AsyncIterator[IngressPacket]:
        while self._running:
            first_recorded_us: int | None = None
            replay_started_us = time.monotonic_ns() // 1000
            for packet in RawSessionReader(self.session_path).packets():
                if not self._running:
                    return
                await self._resume_event.wait()
                if first_recorded_us is None:
                    first_recorded_us = packet.arrival_time_us
                elapsed_recording_us = packet.arrival_time_us - first_recorded_us
                target_us = replay_started_us + int(elapsed_recording_us / self.speed)
                delay_s = (target_us - time.monotonic_ns() // 1000) / 1_000_000
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
                yield IngressPacket(packet.data, time.monotonic_ns() // 1000, "replay")
            if not self.loop:
                self._running = False
