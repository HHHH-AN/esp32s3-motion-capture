from __future__ import annotations

import asyncio
from time import monotonic
from typing import Awaitable, Callable


class LineReassembler:
    def __init__(self, max_bytes: int = 4096, stale_after: float = 1.0) -> None:
        self.max_bytes = max_bytes
        self.stale_after = stale_after
        self._buffer = bytearray()
        self._started_at: float | None = None

    def feed(self, data: bytes, now: float | None = None) -> tuple[list[bytes], int]:
        now = monotonic() if now is None else now
        discarded = 0
        if self._buffer and self._started_at is not None and now - self._started_at > self.stale_after:
            self._buffer.clear(); self._started_at = None; discarded += 1
        if data and not self._buffer:
            self._started_at = now
        self._buffer.extend(data)
        lines: list[bytes] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(self._buffer[:newline]).rstrip(b"\r")
            del self._buffer[:newline + 1]
            if line:
                lines.append(line)
            self._started_at = now if self._buffer else None
        if len(self._buffer) > self.max_bytes:
            self._buffer.clear(); self._started_at = None; discarded += 1
        return lines, discarded


class TcpTransport:
    def __init__(self, host: str, port: int, on_line: Callable[[bytes], Awaitable[None]],
                 on_disconnect: Callable[[str], Awaitable[None]], connect_timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.on_line = on_line
        self.on_disconnect = on_disconnect
        self.connect_timeout = connect_timeout
        self.reassembler = LineReassembler()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._intentional_disconnect = False

    @property
    def is_connected(self) -> bool:
        return bool(self._writer and not self._writer.is_closing())

    async def connect(self) -> None:
        self._intentional_disconnect = False
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), self.connect_timeout)
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
        writer, self._writer = self._writer, None
        self._reader = None
        if writer:
            writer.close()
            await writer.wait_closed()

    async def _read_loop(self) -> None:
        reason = "TCP connection closed"
        try:
            while self._reader:
                data = await self._reader.read(1024)
                if not data:
                    break
                lines, discarded = self.reassembler.feed(data)
                for _ in range(discarded):
                    await self.on_line(b"invalid-partial-frame")
                for line in lines:
                    await self.on_line(line)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = str(exc)
        finally:
            if not self._intentional_disconnect:
                await self.on_disconnect(reason)
