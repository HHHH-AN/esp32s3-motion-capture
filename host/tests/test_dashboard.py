import math
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from time import monotonic

from dashboard.fusion import ComplementaryFusion
from dashboard.kinematics import solve_positions
from dashboard.models import SensorSample, initial_nodes
from dashboard.protocol import CurrentCsvProtocol, FrameError
from dashboard.recordings import RecordingNotFound, catalog, preview_csv, safe_item, session_zip
from dashboard.tcp_transport import LineReassembler
from dashboard.service import Runtime


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = CurrentCsvProtocol()

    def test_parses_current_frame(self):
        sample = self.protocol.parse("0.1,0.2,9.8,1,2,3,26.5,12,13,14,20")
        self.assertEqual(sample.accel, (0.1, 0.2, 9.8))
        self.assertEqual(sample.mag, (12.0, 13.0, 14.0))

    def test_ignores_header(self):
        self.assertIsNone(self.protocol.parse("AccX(g),AccY(g)"))

    def test_rejects_bad_frame(self):
        with self.assertRaises(FrameError):
            self.protocol.parse("1,2,3")
        with self.assertRaises(FrameError):
            self.protocol.parse("0,0,9.8,no,0,0,20,1,2,3,4")


class TcpTransportTests(unittest.TestCase):
    def test_reassembles_fragmented_and_combined_reads(self):
        frames = LineReassembler(max_bytes=64, stale_after=1.0)
        self.assertEqual(frames.feed(b"1,2,", now=0.0), ([], 0))
        self.assertEqual(frames.feed(b"3\n4,5,6\n", now=0.1), ([b"1,2,3", b"4,5,6"], 0))

    def test_discards_overlong_and_stale_partial_frames(self):
        frames = LineReassembler(max_bytes=64, stale_after=1.0)
        self.assertEqual(frames.feed(b"x" * 65, now=0.0), ([], 1))
        self.assertEqual(frames.feed(b"partial", now=1.0), ([], 0))
        self.assertEqual(frames.feed(b"next\n", now=2.1), ([b"next"], 1))


class TransportSelectionTests(unittest.TestCase):
    def test_empty_timeout_has_actionable_endpoint_message(self):
        async def scenario():
            runtime=Runtime(coordinate_file=None)
            from unittest.mock import AsyncMock
            transport=AsyncMock()
            transport.connect.side_effect=TimeoutError()
            with patch.object(runtime,"_new_transport",return_value=transport):
                await runtime.connect(transport="wifi",host="192.168.1.9",tcp_port=9000)
            self.assertEqual(runtime.status,"error")
            self.assertIn("192.168.1.9:9000",runtime.message)
            self.assertIn("超时",runtime.message)
            await runtime.disconnect()
        asyncio.run(scenario())

    def test_disconnect_during_retry_does_not_reconnect(self):
        async def scenario():
            runtime = Runtime(transport="wifi")

            async def disconnect_during_delay(delay):
                await runtime.disconnect()

            with patch("dashboard.service.asyncio.sleep", side_effect=disconnect_during_delay), \
                 patch.object(runtime, "_new_transport") as factory:
                await runtime._transport_disconnected("connection lost")
                factory.assert_not_called()
                self.assertEqual(runtime.status, "disconnected")

        asyncio.run(scenario())

    def test_wifi_line_uses_existing_pipeline(self):
        runtime = Runtime(transport="wifi", host="192.168.1.120", tcp_port=9000)
        asyncio.run(runtime.on_transport_line(b"0.1,0.2,9.8,1,2,3,26.5,12,13,14,20"))
        self.assertEqual(runtime.valid_frames, 1)
        self.assertTrue(runtime.nodes["right_wrist"].valid)
        self.assertEqual(runtime.payload()["stats"]["transport"], "wifi")

    def test_invalid_wifi_line_is_counted(self):
        runtime = Runtime(transport="wifi")
        asyncio.run(runtime.on_transport_line(b"broken"))
        self.assertEqual(runtime.invalid_frames, 1)

    def test_endpoint_validation(self):
        self.assertTrue(Runtime._valid_endpoint("192.168.1.120", 9000))
        self.assertTrue(Runtime._valid_endpoint("imu-node.local", 9000))
        self.assertFalse(Runtime._valid_endpoint("bad host", 9000))
        self.assertFalse(Runtime._valid_endpoint("192.168.1.120", 70000))


class ModelAndFusionTests(unittest.TestCase):
    def test_fourteen_nodes_and_one_real_node(self):
        nodes = initial_nodes()
        self.assertEqual(len(nodes), 14)
        self.assertEqual([n.source for n in nodes.values()].count("real"), 1)
        self.assertEqual(nodes["right_wrist"].source, "real")

    def test_stationary_fusion_is_normalized(self):
        fusion = ComplementaryFusion()
        sample = SensorSample((0, 0, 9.81), (0, 0, 0), (30, 0, 10), 25, 0)
        q = fusion.update(sample)
        self.assertAlmostEqual(math.sqrt(sum(v * v for v in q)), 1.0, places=6)

    def test_virtual_joint_positions_are_deterministic(self):
        first = solve_positions(initial_nodes())
        second = solve_positions(initial_nodes())
        self.assertEqual(first, second)
        self.assertIn("_neck", first)
        self.assertIn("_left_hand_tip", first)
        self.assertIn("_right_toe", first)
        self.assertIn("_face", first)
        self.assertEqual(first["_neck"][0], first["_chest"][0])


class QualityAndRecordingTests(unittest.TestCase):
    def test_gap_estimates_one_lost_packet(self):
        runtime = Runtime()
        base = monotonic()
        runtime._update_quality(base)
        runtime.valid_frames += 1
        runtime._update_quality(base + .05)
        runtime.valid_frames += 1
        runtime._update_quality(base + .15)
        runtime.valid_frames += 1
        self.assertEqual(runtime.estimated_lost, 1)
        self.assertEqual(runtime.quality()["estimated_loss_rate"], 25.0)

    def test_csv_recording_has_bom_and_chinese_header(self):
        runtime = Runtime()
        sample = SensorSample((0, 0, 9.81), (0, 0, 0), (20, 0, 30), 25, 0)
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            runtime.recording_dir = Path(folder) / "recordings"
            os.chdir(folder)
            try:
                runtime.start_recording()
                asyncio.run(runtime.consume(sample))
                record_folder = runtime.record_path
                runtime.stop_recording()
                path = os.path.join(record_folder, "imu-data.csv")
                with open(path, "rb") as handle:
                    self.assertEqual(handle.read(3), b"\xef\xbb\xbf")
                with open(path, encoding="utf-8-sig") as handle:
                    self.assertIn("节点名称", handle.readline())
            finally:
                os.chdir(previous)

    def test_catalog_preview_zip_and_path_safety(self):
        runtime = Runtime()
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            runtime.recording_dir = Path(folder) / "recordings"
            os.chdir(folder)
            try:
                runtime.start_recording()
                session = os.path.basename(runtime.record_path)
                asyncio.run(runtime.consume(SensorSample((0, 0, 9.81), (0, 0, 0), (20, 0, 30), 25, 1)))
                runtime.stop_recording()
                self.assertEqual(catalog(runtime.recording_dir)[0]["id"], session)
                preview = preview_csv(session, "imu-data.csv", root=runtime.recording_dir)
                self.assertEqual(preview["total_rows"], 1)
                self.assertGreater(len(session_zip(session, runtime.recording_dir)), 100)
                with self.assertRaises(RecordingNotFound):
                    safe_item("../outside")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
