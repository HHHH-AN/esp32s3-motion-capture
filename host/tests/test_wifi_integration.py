import asyncio
import contextlib
import io
import unittest

from dashboard.protocol import CurrentCsvProtocol
from dashboard.tcp_transport import TcpTransport
from receive_wifi import receive


FRAME = b"0.1,0.2,0.98,1,2,3,26.5,12,13,14,20\n"


class WifiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_receives_fragmented_and_combined_sensor_frames(self):
        samples = []
        received = asyncio.Event()
        release = asyncio.Event()

        async def device(reader, writer):
            try:
                writer.write(FRAME[:9])
                await writer.drain()
                await asyncio.sleep(.01)
                writer.write(FRAME[9:] + FRAME)
                await writer.drain()
                await release.wait()
            finally:
                writer.close()
                await writer.wait_closed()

        async def on_line(raw):
            samples.append(CurrentCsvProtocol().parse(raw.decode()))
            if len(samples) == 2:
                received.set()

        async def on_disconnect(reason):
            self.fail(reason)

        server = await asyncio.start_server(device, "127.0.0.1", 0)
        transport = TcpTransport("127.0.0.1", server.sockets[0].getsockname()[1], on_line, on_disconnect)
        try:
            await transport.connect()
            await asyncio.wait_for(received.wait(), 2)
            self.assertEqual(samples[0].accel, (.1, .2, .98))
            self.assertEqual(samples[1].mag, (12, 13, 14))
        finally:
            await transport.disconnect()
            release.set()
            server.close()
            await server.wait_closed()

    async def test_silent_connection_times_out_and_closes_socket(self):
        closed = asyncio.Event()
        disconnected = asyncio.Event()
        reasons = []

        async def device(reader, writer):
            try:
                await reader.read()
                closed.set()
            finally:
                writer.close()
                await writer.wait_closed()

        async def on_line(raw):
            self.fail("Silent device emitted a frame")

        async def on_disconnect(reason):
            reasons.append(reason)
            disconnected.set()

        server = await asyncio.start_server(device, "127.0.0.1", 0)
        transport = TcpTransport("127.0.0.1", server.sockets[0].getsockname()[1], on_line, on_disconnect,
                                 read_timeout=.05)
        try:
            await transport.connect()
            await asyncio.wait_for(disconnected.wait(), 2)
            await asyncio.wait_for(closed.wait(), 2)
            self.assertIn("timeout", reasons[0])
            self.assertFalse(transport.is_connected)
        finally:
            await transport.disconnect()
            server.close()
            await server.wait_closed()

    async def test_terminal_receiver_prints_valid_frames(self):
        async def device(reader, writer):
            writer.write(FRAME + FRAME)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(device, "127.0.0.1", 0)
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                await asyncio.to_thread(receive, "127.0.0.1", server.sockets[0].getsockname()[1], 2)
            self.assertEqual(output.getvalue().splitlines()[1:], [FRAME.decode().strip()] * 2)
        finally:
            server.close()
            await server.wait_closed()
