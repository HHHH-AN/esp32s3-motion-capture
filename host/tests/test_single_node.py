import asyncio
import csv
import io
import math
from pathlib import Path
import tempfile
import unittest
import zipfile

from dashboard.fusion import ComplementaryFusion, euler_quaternion, relative, euler_degrees
from dashboard.models import SensorSample
from dashboard.protocol import CurrentCsvProtocol, FrameError
from dashboard.recordings import replay_data, session_zip
from dashboard.service import Runtime


def frame(sequence=0, device_us=0, flags=3):
    return f"IMU2,right_wrist,{sequence},{device_us},{flags},0,0,1,0,0,0,25,30,0,10,0"


class SingleNodeTests(unittest.TestCase):
    def test_v2_metadata_and_flags(self):
        sample = CurrentCsvProtocol().parse(frame(45, 10000, 1))
        self.assertEqual((sample.sequence, sample.device_us, sample.sensor_flags), (45,10000,1))
        for line in [frame(-1), frame(device_us=2**32), frame(flags=4), frame().replace("right_wrist", "../../bad")]:
            with self.assertRaises(FrameError):
                CurrentCsvProtocol().parse(line)

    def test_sequence_counts_missing_frames_and_rejects_duplicates(self):
        async def scenario():
            runtime=Runtime()
            for seq in [10, 11, 14, 14]:
                await runtime.on_transport_line(frame(seq,seq*10000).encode())
            self.assertEqual(runtime.valid_frames, 3)
            self.assertEqual(runtime.estimated_lost, 2)
            self.assertEqual(runtime.duplicate_frames, 1)
            self.assertEqual(len(runtime.payload()["nodes"]), 1)
        asyncio.run(scenario())

    def test_sequence_wrap_and_device_restart(self):
        async def scenario():
            runtime=Runtime()
            for seq in [2**32-1,0,1,0]:
                await runtime.on_transport_line(frame(seq,seq%100*10000).encode())
            self.assertEqual(runtime.estimated_lost,0)
            self.assertEqual(runtime.device_restarts,1)
        asyncio.run(scenario())

    def test_fusion_uses_device_time_when_packets_arrive_together(self):
        fusion=ComplementaryFusion()
        for seq in range(101):
            sample=SensorSample((0,0,0),(0,0,90),(0,0,0),25,0,
                                received_monotonic=1.0,device_us=seq*10000)
            q=fusion.update(sample)
        self.assertGreater(q[3], .70)
        self.assertLess(q[3], .73)

    def test_device_time_wrap(self):
        fusion=ComplementaryFusion()
        first=SensorSample((0,0,0),(0,0,0),(0,0,0),25,0,device_us=2**32-5000)
        second=SensorSample((0,0,0),(0,0,100),(0,0,0),25,0,device_us=5000)
        fusion.update(first)
        q=fusion.update(second)
        self.assertAlmostEqual(q[3],math.sin(math.radians(1)/2),places=5)

    def test_relative_zero_is_identity(self):
        q=euler_quaternion(.4,.2,-.8)
        result=relative(q,q)
        for actual,expected in zip(result,(1,0,0,0)):
            self.assertAlmostEqual(actual,expected)

    def test_motion_correction_does_not_treat_horizontal_acceleration_as_large_tilt(self):
        fusion=ComplementaryFusion()
        fusion.update(SensorSample((0,0,1),(0,0,0),(30,0,10),25,0,device_us=0))
        for i in range(1,101):
            fusion.update(SensorSample((.1,0,1),(0,0,0),(30,0,10),25,0,device_us=i*10000),correction_scale=.05)
        self.assertLess(abs(euler_degrees(fusion.q)[1]),.2)

    def test_stale_node_becomes_invalid(self):
        async def scenario():
            runtime=Runtime()
            sample=SensorSample((0,0,1),(0,0,0),(30,0,0),25,0,received_monotonic=0)
            await runtime.consume(sample)
            self.assertFalse(runtime.payload()["nodes"][0]["valid"])
        asyncio.run(scenario())

    def test_stationary_gyro_calibration(self):
        async def scenario():
            runtime=Runtime()
            await runtime.consume(SensorSample((0,0,1),(1,2,3),(30,0,0),25,0))
            await runtime.command({"action":"calibrate"})
            for i in range(32):
                await runtime.consume(SensorSample((0,0,1),(1,2,3),(30,0,0),25,0,received_monotonic=100+i*.1))
            self.assertEqual(runtime._gyro_bias,(1,2,3))
            self.assertIsNone(runtime._calibration)
        asyncio.run(scenario())

    def test_moving_node_cancels_calibration(self):
        runtime=Runtime()
        runtime._calibration={"start":None,"count":0,"sum":[0,0,0]}
        runtime._update_calibration(SensorSample((0,0,2),(0,0,0),(30,0,0),25,0))
        self.assertIsNone(runtime._calibration)
        self.assertIn("取消",runtime.calibration_message)

    def test_recording_is_unique_and_exports_original_metadata(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as temp:
                runtime=Runtime(recording_dir=Path(temp))
                runtime.start_recording()
                await runtime.on_transport_line(frame(6,123456).encode())
                first=Path(runtime.record_path)
                runtime.stop_recording()
                runtime.start_recording()
                self.assertNotEqual(first,Path(runtime.record_path))
                runtime.stop_recording()
                with (first/"imu-data.csv").open(encoding="utf-8-sig") as handle:
                    row=next(csv.DictReader(handle))
                self.assertEqual(row["帧序号"],"6")
                self.assertEqual(row["设备采样微秒"],"123456")
                replay=replay_data(first.name,Path(temp))
                self.assertEqual(len(replay["frames"]),1)
                with zipfile.ZipFile(io.BytesIO(session_zip(first.name,Path(temp)))) as archive:
                    self.assertIn(first.name+"/metadata.json",archive.namelist())
        asyncio.run(scenario())

    def test_bad_command_does_not_break_connection(self):
        async def scenario():
            runtime=Runtime()
            await runtime.command({"action":"connect","transport":"wifi","tcp_port":"abc"})
            self.assertEqual(runtime.status,"error")
            await runtime.command([])
            self.assertIn("JSON",runtime.message)
        asyncio.run(scenario())
