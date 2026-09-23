from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from mocap_pose.domain.models import IngressPacket

from .base import PacketSource
from .ble_fragments import BleFragmentReassembler


class BleSource(PacketSource):
    """Bleak notification source with bounded buffering and automatic reconnect."""

    def __init__(
        self,
        data_characteristic: str,
        address: str | None = None,
        name_prefix: str = "MOCAP-",
        queue_capacity: int = 2048,
        reconnect_delay_s: float = 2.0,
    ) -> None:
        self.data_characteristic = data_characteristic
        self.address = address
        self.name_prefix = name_prefix
        self.reconnect_delay_s = reconnect_delay_s
        self._queue: asyncio.Queue[IngressPacket] = asyncio.Queue(queue_capacity)
        self._running = False
        self._connection_enabled = True
        self._worker: asyncio.Task[None] | None = None
        self._client = None
        self.dropped_notifications = 0
        self.reassembler = BleFragmentReassembler()

    async def start(self) -> None:
        self._running = True
        self._worker = asyncio.create_task(self._connection_loop(), name="ble-source")

    async def stop(self) -> None:
        self._running = False
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    async def connect(self, address: str) -> None:
        self.address = address
        self._connection_enabled = True
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()

    async def disconnect(self) -> None:
        self._connection_enabled = False
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()

    def _on_notification(self, _sender: object, data: bytearray) -> None:
        now_us = time.monotonic_ns() // 1000
        frame = self.reassembler.push(bytes(data), now_us)
        if frame is None:
            return
        packet = IngressPacket(frame, now_us, "ble")
        try:
            self._queue.put_nowait(packet)
        except asyncio.QueueFull:
            self.dropped_notifications += 1

    async def _find_address(self) -> str:
        if self.address:
            return self.address
        from bleak import BleakScanner

        devices = await BleakScanner.discover(timeout=5.0)
        for device in devices:
            if (device.name or "").startswith(self.name_prefix):
                return device.address
        raise RuntimeError(f"no BLE device with prefix {self.name_prefix!r} found")

    async def _connection_loop(self) -> None:
        from bleak import BleakClient

        while self._running:
            if not self._connection_enabled:
                await asyncio.sleep(0.25)
                continue
            try:
                address = await self._find_address()
                if not self._connection_enabled:
                    continue
                async with BleakClient(address) as client:
                    self._client = client
                    await client.start_notify(self.data_characteristic, self._on_notification)
                    while self._running and client.is_connected:
                        await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(self.reconnect_delay_s)
            finally:
                self._client = None

    async def packets(self) -> AsyncIterator[IngressPacket]:
        while self._running:
            yield await self._queue.get()
