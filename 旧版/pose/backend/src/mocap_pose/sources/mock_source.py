from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator

from mocap_pose.domain.models import IngressPacket, RawImuSample
from mocap_pose.protocol.encoder import encode_raw_sample

from .base import PacketSource


class MockSource(PacketSource):
    """Deterministic 100 Hz synthetic IMU source for hardware-free integration."""

    def __init__(self, node_ids: tuple[int, ...] = (1,), sample_rate_hz: int = 100) -> None:
        self.node_ids = node_ids
        self.sample_rate_hz = sample_rate_hz
        self._running = False
        self._sequence = {node_id: 0 for node_id in node_ids}
        self._start_ns = 0

    async def start(self) -> None:
        self._start_ns = time.monotonic_ns()
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def packets(self) -> AsyncIterator[IngressPacket]:
        interval = 1.0 / self.sample_rate_hz
        next_tick = time.monotonic()
        while self._running:
            elapsed_s = (time.monotonic_ns() - self._start_ns) / 1_000_000_000
            timestamp_us = int(elapsed_s * 1_000_000)
            for index, node_id in enumerate(self.node_ids):
                phase = elapsed_s * 0.7 + index * 0.15
                sample = RawImuSample(
                    node_id=node_id,
                    sequence=self._sequence[node_id],
                    device_timestamp_us=timestamp_us,
                    accel_mg=(int(30 * math.sin(phase)), 0, 1000),
                    gyro_dps_x10=(0, 0, int(180 * math.cos(phase))),
                    mag_ut_x10=(450, int(-80 * math.sin(phase)), 120),
                    temperature_c_x100=2500,
                    mag_age_us=0,
                    status_flags=0x000F,
                )
                self._sequence[node_id] = (self._sequence[node_id] + 1) & 0xFFFFFFFF
                yield IngressPacket(encode_raw_sample(sample), time.monotonic_ns() // 1000, "mock")
            next_tick += interval
            await asyncio.sleep(max(0.0, next_tick - time.monotonic()))
