from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from mocap_pose.domain.models import IngressPacket

from .base import PacketSource


class SerialSource(PacketSource):
    def __init__(self, port: str, baudrate: int = 921_600, read_size: int = 1024) -> None:
        self.port = port
        self.baudrate = baudrate
        self.read_size = read_size
        self._serial = None
        self._running = False

    async def start(self) -> None:
        import serial

        self._serial = serial.Serial(self.port, self.baudrate, timeout=0.1)
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._serial is not None:
            await asyncio.to_thread(self._serial.close)
            self._serial = None

    async def packets(self) -> AsyncIterator[IngressPacket]:
        if self._serial is None:
            raise RuntimeError("SerialSource.start() must be called first")
        while self._running:
            data = await asyncio.to_thread(self._serial.read, self.read_size)
            if data:
                yield IngressPacket(data, time.monotonic_ns() // 1000, "serial")

