from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import serial


class SerialTransport:
    def __init__(self, port: str, baudrate: int, on_line: Callable[[bytes], Awaitable[None]],
                 on_disconnect: Callable[[str], Awaitable[None]]) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_line = on_line
        self.on_disconnect = on_disconnect
        self._serial: serial.Serial | None = None
        self._reader_task: asyncio.Task | None = None
        self._intentional_disconnect = False

    @property
    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    async def connect(self) -> None:
        self._intentional_disconnect = False
        self._serial = serial.Serial(self.port, self.baudrate, timeout=0.25)
        self._reader_task = asyncio.create_task(self._read_loop())

    async def disconnect(self) -> None:
        self._intentional_disconnect = True
        task, self._reader_task = self._reader_task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    async def _read_loop(self) -> None:
        try:
            while self._serial and self._serial.is_open:
                raw = await asyncio.to_thread(self._serial.readline)
                if raw:
                    await self.on_line(raw.rstrip(b"\r\n"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._intentional_disconnect:
                await self.on_disconnect(str(exc))
