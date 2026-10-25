import asyncio
import importlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from urllib.request import urlopen
import zipfile

import uvicorn
from websockets.asyncio.client import connect

from dashboard.service import Runtime


class AppIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_websocket_recording_replay_export(self):
        module = importlib.import_module("dashboard.app")
        previous = module.runtime
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(10)
        http_port = sock.getsockname()[1]
        device_tasks = set()
        release = asyncio.Event()

        async def device(reader, writer):
            task=asyncio.current_task()
            device_tasks.add(task)
            try:
                sequence=0
                while not release.is_set():
                    writer.write(f"IMU2,right_wrist,{sequence},{sequence*10000},3,0,0,1,0,0,0,25,30,0,10,0\n".encode())
                    await writer.drain()
                    sequence+=1
                    await asyncio.sleep(.01)
            except (ConnectionError, asyncio.CancelledError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                device_tasks.discard(task)

        async def receive_until(ws, predicate):
            async def wait():
                while True:
                    frame=json.loads(await ws.recv())
                    if predicate(frame):
                        return frame
            try:
                return await asyncio.wait_for(wait(), 5)
            except asyncio.TimeoutError:
                self.fail(f"Timed out: {module.runtime.payload()['stats']}; clients={len(module.runtime.clients)}; heartbeat={module.runtime._heartbeat_task}")

        def get(path):
            with urlopen(f"http://127.0.0.1:{http_port}{path}",timeout=5) as response:
                return response.read()

        with tempfile.TemporaryDirectory() as folder:
            module.runtime=Runtime(recording_dir=Path(folder))
            server=uvicorn.Server(uvicorn.Config(module.app,log_level="error",access_log=False))
            task=asyncio.create_task(server.serve(sockets=[sock]))
            device_server=await asyncio.start_server(device,"127.0.0.1",0)
            try:
                for _ in range(200):
                    if server.started:
                        break
                    if task.done():
                        await task
                    await asyncio.sleep(.01)
                self.assertTrue(server.started)
                html=await asyncio.to_thread(get,"/")
                self.assertIn("单节点开发台".encode(),html)
                self.assertNotIn(b"cdn.jsdelivr",html)
                async with connect(f"ws://127.0.0.1:{http_port}/ws") as ws:
                    await ws.send(json.dumps({"action":"connect","transport":"wifi","host":"127.0.0.1",
                                              "tcp_port":device_server.sockets[0].getsockname()[1]}))
                    data=await receive_until(ws,lambda p:p["stats"]["valid_frames"]>=5 and p["motion"]["phase"]=="measuring")
                    self.assertEqual(len(data["nodes"]),1)
                    await ws.send(json.dumps({"action":"start_recording"}))
                    await receive_until(ws,lambda p:p["stats"]["record_rows"]>=5)
                    await ws.send(json.dumps({"action":"stop_recording"}))
                    data=await receive_until(ws,lambda p:not p["stats"]["recording"] and p["stats"]["record_rows"]>=5)
                    session=Path(data["stats"]["record_path"]).name
                    # These routes share the project's catalog root in production.
                    from unittest.mock import patch
                    with patch("dashboard.recordings.recording_root",return_value=Path(folder).resolve()):
                        replay=json.loads(await asyncio.to_thread(get,f"/api/recordings/{session}/replay"))
                        self.assertGreaterEqual(len(replay["frames"]),5)
                        self.assertGreater(replay["duration_s"],0)
                        self.assertTrue(replay["frames"][-1]["motion"]["zupt"])
                        self.assertEqual(replay["frames"][-1]["motion"]["quality"],"stationary_constraint")
                        export=await asyncio.to_thread(get,f"/api/recordings/{session}/download")
                        with zipfile.ZipFile(io.BytesIO(export)) as archive:
                            self.assertIn(f"{session}/imu-data.csv",archive.namelist())
                    await ws.send("invalid JSON")
                    await ws.send(json.dumps({"action":"disconnect"}))
                    await receive_until(ws,lambda p:p["stats"]["serial_status"]=="disconnected")
            finally:
                release.set()
                server.should_exit=True
                await asyncio.wait_for(task,5)
                device_server.close()
                await device_server.wait_closed()
                if device_tasks:
                    await asyncio.wait_for(asyncio.gather(*device_tasks),2)
                sock.close()
                module.runtime=previous
