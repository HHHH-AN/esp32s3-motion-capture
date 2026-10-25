from __future__ import annotations

import asyncio
from time import monotonic
from typing import Awaitable, Callable

import serial
from .tcp_transport import LineReassembler


class SerialTransport:
    def __init__(self, port: str, baudrate: int, on_line: Callable[[bytes], Awaitable[None]],
                 on_disconnect: Callable[[str], Awaitable[None]], read_timeout: float = 3.0,
                 startup_timeout: float = 8.0, connect_timeout: float = 5.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_line = on_line
        self.on_disconnect = on_disconnect
        self._serial: serial.Serial | None = None
        self._reader_task: asyncio.Task | None = None
        self._intentional_disconnect = False
        self._closing = False
        self.read_timeout, self.startup_timeout = read_timeout, startup_timeout
        self.connect_timeout = connect_timeout
        self._close_task = None
        self.reassembler = LineReassembler()

    @property
    def is_connected(self) -> bool:
        return bool(not self._intentional_disconnect and not self._closing
                    and self._serial and self._serial.is_open)

    async def connect(self) -> None:
        self._intentional_disconnect = False
        self._closing = False
        self._close_task = None
        self.reassembler = LineReassembler()
        opening = asyncio.create_task(asyncio.to_thread(
            serial.Serial, self.port, self.baudrate, timeout=0.25))
        try:
            self._serial = await asyncio.wait_for(asyncio.shield(opening), self.connect_timeout)
        except (TimeoutError, asyncio.CancelledError):
            # A Windows driver call is not cancelled with its awaiting coroutine.
            # Retain ownership and close a late result, rather than leaking COM9.
            self._intentional_disconnect = True
            self._reader_task = asyncio.create_task(self._finish_late_open(opening))
            raise TimeoutError(f"打开串口 {self.port} 超时；USB 驱动未响应，请重新插拔板子后重试")
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _finish_late_open(self, opening):
        try:
            self._serial = await opening
        except Exception:
            return
        await self._close_port(self._serial)

    async def _close_port(self, handle):
        self._closing = True
        if handle and handle.is_open:
            if self._close_task is None:
                self._close_task = asyncio.create_task(asyncio.to_thread(handle.close))
            await asyncio.shield(self._close_task)
        if self._serial is handle:
            self._serial = None

    async def disconnect(self) -> None:
        self._intentional_disconnect = True
        handle, task = self._serial, self._reader_task
        try:
            if handle and handle.is_open and not self._closing:
                cancel_read = getattr(handle, "cancel_read", None)
                if cancel_read:
                    await asyncio.wait_for(asyncio.to_thread(cancel_read), 1.0)
            # Never cancel to_thread(read) and then close its live Windows handle.
            if task and task is not asyncio.current_task():
                await asyncio.wait_for(asyncio.shield(task), 2.0)
            elif handle:
                await asyncio.wait_for(self._close_port(handle), 2.0)
        except TimeoutError as exc:
            raise OSError(f"串口 {self.port} 驱动未完成关闭；请拔插 USB 板子后重试") from exc
        self._reader_task = None

    @staticmethod
    def _read_chunk(handle):
        size = max(1, min(handle.in_waiting, 4096))
        return handle.read(size)

    async def _read_loop(self) -> None:
        handle = self._serial
        last_data, received = monotonic(), False
        reason = None
        try:
            while not self._intentional_disconnect and handle and handle.is_open:
                raw = await asyncio.to_thread(self._read_chunk, handle)
                if self._intentional_disconnect:
                    break
                if raw:
                    last_data, received = monotonic(), True
                    lines, discarded = self.reassembler.feed(raw)
                    for _ in range(discarded):
                        await self.on_line(b"invalid-partial-frame")
                    for line in lines:
                        await self.on_line(line)
                elif monotonic() - last_data >= (self.read_timeout if received else self.startup_timeout):
                    raise TimeoutError(f"串口 {self.port} 已打开但{'停止输出' if received else '未收到'}数据；"
                                       "请检查板子供电、USB 连接和正在运行的固件")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
        finally:
            self._closing = True
            await self._close_port(handle)
            if reason and not self._intentional_disconnect:
                await self.on_disconnect(reason)
