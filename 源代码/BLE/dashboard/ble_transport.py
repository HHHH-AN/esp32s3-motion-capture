from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Awaitable, Callable


DEVICE_NAME = "IMU-MOTION-01"
SERVICE_UUID = "7d2a0001-6c8a-4f6b-9c65-4f4d55494d55"
NOTIFY_UUID = "7d2a0002-6c8a-4f6b-9c65-4f4d55494d55"


class LineReassembler:
    """Reassemble newline-delimited frames from arbitrary BLE fragments."""

    def __init__(self, max_bytes: int = 4096, stale_after: float = 1.0) -> None:
        self.max_bytes = max_bytes
        self.stale_after = stale_after
        self._buffer = bytearray()
        self._started_at: float | None = None

    def feed(self, data: bytes, now: float | None = None) -> tuple[list[bytes], int]:
        now = monotonic() if now is None else now
        discarded = 0
        if self._buffer and self._started_at is not None and now - self._started_at > self.stale_after:
            self._buffer.clear()
            self._started_at = None
            discarded += 1

        if data and not self._buffer:
            self._started_at = now
        self._buffer.extend(data)

        lines: list[bytes] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(self._buffer[:newline]).rstrip(b"\r")
            del self._buffer[: newline + 1]
            if line:
                lines.append(line)
            self._started_at = now if self._buffer else None

        if len(self._buffer) > self.max_bytes:
            self._buffer.clear()
            self._started_at = None
            discarded += 1
        return lines, discarded


@dataclass(frozen=True)
class BleDeviceInfo:
    address: str
    name: str


async def scan_imu_devices(timeout: float = 5.0) -> list[BleDeviceInfo]:
    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=timeout)
    matched = {
        device.address: BleDeviceInfo(device.address, device.name or DEVICE_NAME)
        for device in devices
        if device.name == DEVICE_NAME
    }
    return sorted(matched.values(), key=lambda item: item.address)


class BleTransport:
    def __init__(
        self,
        device: str,
        on_line: Callable[[bytes], Awaitable[None]],
        on_disconnect: Callable[[str], Awaitable[None]],
    ) -> None:
        self.device = device
        self.on_line = on_line
        self.on_disconnect = on_disconnect
        self.reassembler = LineReassembler()
        self.invalid_fragments = 0
        self._client = None
        self._intentional_disconnect = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    async def connect(self) -> None:
        from bleak import BleakClient

        self._loop = asyncio.get_running_loop()
        self._intentional_disconnect = False
        self._client = BleakClient(self.device, disconnected_callback=self._disconnected)
        await self._client.connect()
        await self._client.start_notify(NOTIFY_UUID, self._notification)

    async def disconnect(self) -> None:
        self._intentional_disconnect = True
        client, self._client = self._client, None
        if client and client.is_connected:
            try:
                await client.stop_notify(NOTIFY_UUID)
            finally:
                await client.disconnect()

    def _notification(self, _sender, data: bytearray) -> None:
        lines, discarded = self.reassembler.feed(bytes(data))
        self.invalid_fragments += discarded
        if self._loop:
            for line in lines:
                self._loop.create_task(self.on_line(line))

    def _disconnected(self, _client) -> None:
        if self._intentional_disconnect or not self._loop:
            return
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self.on_disconnect("BLE connection lost"))
        )
