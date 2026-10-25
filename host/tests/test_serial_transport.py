import asyncio
from collections import deque
import threading
import time
import unittest
from unittest.mock import patch

from dashboard.serial_transport import SerialTransport


class FakeSerial:
    """Thread-safe serial stand-in; never opens a Windows device."""

    def __init__(self, chunks=(), *, blocking=False):
        self.is_open = True
        self.chunks = deque(chunks)
        self.blocking = blocking
        self.condition = threading.Condition()
        self.cancelled = False
        self.read_started = threading.Event()
        self.active_reads = 0
        self.read_sizes = []
        self.events = []
        self.close_thread = None
        self.closed_while_reading = False
        self.close_count = 0

    @property
    def in_waiting(self):
        with self.condition:
            return sum(len(chunk) if isinstance(chunk, bytes) else 1 for chunk in self.chunks)

    def read(self, size=1):
        with self.condition:
            self.active_reads += 1
            self.read_sizes.append(size)
            self.events.append("read_start")
            self.read_started.set()
            try:
                if not self.chunks and self.is_open and not self.cancelled:
                    self.condition.wait(None if self.blocking else .005)
                if self.cancelled or not self.is_open or not self.chunks:
                    return b""
                chunk = self.chunks.popleft()
                if isinstance(chunk, BaseException):
                    raise chunk
                result, remaining = chunk[:size], chunk[size:]
                if remaining:
                    self.chunks.appendleft(remaining)
                return result
            finally:
                self.active_reads -= 1
                self.events.append("read_end")

    def cancel_read(self):
        with self.condition:
            self.cancelled = True
            self.events.append("cancel_read")
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.close_count += 1
            self.close_thread = threading.get_ident()
            self.closed_while_reading |= self.active_reads != 0
            self.events.append("close")
            self.is_open = False
            self.condition.notify_all()


class SerialTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connections = []

    async def asyncTearDown(self):
        for transport, fake in self.connections:
            # Also release the fake if the implementation under test failed.
            fake.cancel_read()
            await asyncio.wait_for(transport.disconnect(), 1)

    async def make_transport(self, fake, *, read_timeout=1, startup_timeout=1):
        lines, reasons = [], []
        received, disconnected = asyncio.Event(), asyncio.Event()

        async def on_line(raw):
            lines.append(raw)
            received.set()

        async def on_disconnect(reason):
            reasons.append(reason)
            disconnected.set()

        transport = SerialTransport("COM_TEST", 115200, on_line, on_disconnect,
                                    read_timeout=read_timeout, startup_timeout=startup_timeout)
        self.connections.append((transport, fake))
        with patch("dashboard.serial_transport.serial.Serial", return_value=fake):
            await transport.connect()
        return transport, lines, reasons, received, disconnected

    async def test_block_reads_reassemble_fragmented_and_combined_lines(self):
        fake = FakeSerial([b"IMU2,node,1", b",0,3\r\nIMU2,node,2,10000,3\n"])
        transport, lines, reasons, _, _ = await self.make_transport(fake)
        deadline = time.monotonic() + 1
        while len(lines) < 2 and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        self.assertEqual(lines, [b"IMU2,node,1,0,3", b"IMU2,node,2,10000,3"])
        self.assertTrue(any(size > 1 for size in fake.read_sizes), "Use block reads rather than byte-wise read_until")
        await transport.disconnect()
        self.assertEqual(reasons, [])

    async def test_silence_after_data_times_out_and_closes_once(self):
        fake = FakeSerial([b"sensor-frame\n"])
        transport, lines, reasons, received, disconnected = await self.make_transport(
            fake, read_timeout=.05, startup_timeout=.5)
        await asyncio.wait_for(received.wait(), 1)
        await asyncio.wait_for(disconnected.wait(), 1)
        self.assertEqual(lines, [b"sensor-frame"])
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].strip())
        self.assertFalse(transport.is_connected)
        self.assertFalse(fake.is_open)
        await transport.disconnect()
        self.assertEqual(len(reasons), 1)
        self.assertEqual(fake.close_count, 1)

    async def test_first_data_has_longer_startup_grace(self):
        fake = FakeSerial()
        transport, _, reasons, _, disconnected = await self.make_transport(
            fake, read_timeout=.04, startup_timeout=.2)
        await asyncio.sleep(.09)
        self.assertTrue(transport.is_connected, "No first byte yet: use startup_timeout, not read_timeout")
        self.assertEqual(reasons, [])
        await asyncio.wait_for(disconnected.wait(), 1)
        self.assertEqual(len(reasons), 1)
        self.assertFalse(transport.is_connected)

    async def test_disconnect_wakes_blocked_read_before_closing_off_loop(self):
        fake = FakeSerial(blocking=True)
        transport, _, reasons, _, _ = await self.make_transport(fake)
        self.assertTrue(await asyncio.to_thread(fake.read_started.wait, .5))
        loop_thread = threading.get_ident()
        await asyncio.wait_for(transport.disconnect(), .5)
        self.assertIn("cancel_read", fake.events)
        self.assertFalse(fake.closed_while_reading)
        self.assertLess(fake.events.index("cancel_read"), fake.events.index("read_end"))
        self.assertLess(fake.events.index("read_end"), fake.events.index("close"))
        self.assertNotEqual(fake.close_thread, loop_thread, "Driver close must not block the HTTP event loop")
        self.assertFalse(transport.is_connected)
        self.assertEqual(reasons, [])

    async def test_read_exception_notifies_once_and_closes(self):
        fake = FakeSerial([OSError("USB device disconnected")])
        transport, lines, reasons, _, disconnected = await self.make_transport(fake)
        await asyncio.wait_for(disconnected.wait(), 1)
        self.assertEqual(lines, [])
        self.assertEqual(len(reasons), 1)
        self.assertIn("USB device disconnected", reasons[0])
        self.assertFalse(transport.is_connected)
        await transport.disconnect()
        self.assertEqual(len(reasons), 1)
        self.assertEqual(fake.close_count, 1)

    async def test_normal_disconnect_has_no_error_callback(self):
        fake = FakeSerial([b"sample\n"])
        transport, lines, reasons, received, _ = await self.make_transport(fake)
        await asyncio.wait_for(received.wait(), 1)
        await transport.disconnect()
        await transport.disconnect()
        self.assertEqual(lines, [b"sample"])
        self.assertEqual(reasons, [])
        self.assertFalse(transport.is_connected)
        self.assertEqual(fake.close_count, 1)


if __name__ == "__main__":
    unittest.main()
