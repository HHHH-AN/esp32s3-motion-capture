"""Physical invariants, failure boundaries, replay provenance and TCP capture."""
import asyncio
import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dashboard.fusion import euler_quaternion, multiply
from motion_presets.engine import ExperimentError, analyse, axis_angle, inverse, rotation_angle
from motion_presets.sources import RAW_FIELDS, capture_tcp, demo_rows
from run_motion_presets import ROOT, load_settings, main


AXES = [["-X", "+Y", "-Z"] for _ in range(3)]
TEST_TEMP = ROOT / "preset_runs" / "test_temp"
TEST_TEMP.mkdir(parents=True, exist_ok=True)


def preset(name):
    return json.loads((ROOT / "presets" / f"{name}.json").read_text(encoding="utf-8"))


class PresetGeometryTests(unittest.TestCase):
    def test_common_world_rotation_does_not_change_joint_angle(self):
        parent = euler_quaternion(.2, -.3, 2.9)
        child = multiply(parent, euler_quaternion(0, math.pi/2, .4))
        world = euler_quaternion(-.5, .7, -2.8)
        self.assertAlmostEqual(axis_angle(parent, child), 90, places=7)
        self.assertAlmostEqual(axis_angle(multiply(world, parent), multiply(world, child)), 90, places=7)

    def test_axial_rotation_is_not_mislabelled_as_flexion(self):
        self.assertAlmostEqual(axis_angle((1, 0, 0, 0), euler_quaternion(0, 0, 1.3)), 0, places=7)
        self.assertAlmostEqual(rotation_angle(euler_quaternion(0, 0, math.radians(179)),
                                              euler_quaternion(0, 0, math.radians(-179))), 2, places=7)


class PresetAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = preset("upper_limb")
        cls.rows = list(demo_rows(cls.config, 16, AXES))

    def test_known_elbow_range_and_repetitions_with_arbitrary_mounts(self):
        result = analyse(self.config, self.rows, AXES)
        self.assertAlmostEqual(result["metrics"]["elbow"]["max_deg"], 90, delta=.4)
        self.assertAlmostEqual(result["metrics"]["arm_trunk"]["max_deg"], 25, delta=.4)
        self.assertEqual(result["repetitions"]["elbow"]["count"], 3)
        self.assertAlmostEqual(result["repetitions"]["elbow"]["mean_period_s"], 4, delta=.04)
        self.assertEqual(result["invalid_aligned_frames"], 0)

    def test_rigid_body_motion_keeps_relative_orientation(self):
        config = preset("rigid_check")
        result = analyse(config, list(demo_rows(config, 12, AXES)), AXES)
        self.assertLess(result["metrics"]["ab"]["max_deg"], .2)
        self.assertLess(result["metrics"]["ac"]["max_deg"], .2)

    def test_different_boot_times_and_microsecond_wrap_are_supported(self):
        result = analyse(self.config, self.rows, AXES)
        self.assertGreater(result["nodes"]["C"]["clock_offset_estimate_s"]*-1, 4000)
        for node in result["nodes"].values():
            self.assertAlmostEqual(node["estimated_sample_rate_hz"], 100, delta=.01)
            self.assertEqual(node["lost_sequence_frames"], 0)

    def test_short_missing_interval_is_left_blank(self):
        damaged = [r for r in self.rows if not (r["slot"] == "B" and 6 < float(r["arrival_s"]) < 6.13)]
        result = analyse(self.config, damaged, AXES)
        self.assertGreater(result["invalid_aligned_frames"], 0)
        self.assertGreater(result["nodes"]["B"]["lost_sequence_frames"], 0)
        for frame in result["frames"]:
            if not frame["valid"]:
                self.assertEqual(frame["angles"], {})

    def test_raw_rate_gyro_peak_is_not_lost_to_display_resampling(self):
        changed = [dict(row) for row in self.rows]
        row = next(r for r in changed if r["slot"] == "A" and float(r["arrival_s"]) == 6.01)
        parts = row["line"].split(",")
        parts[8:11] = ["123", "0", "0"]
        row["line"] = ",".join(parts)
        result = analyse(self.config, changed, AXES)
        self.assertAlmostEqual(result["peak_sensor_gyro_dps"]["A"], 123, places=5)

    def test_long_gap_stops_instead_of_integrating_missing_motion(self):
        damaged = [r for r in self.rows if not (r["slot"] == "B" and 6 < float(r["arrival_s"]) < 6.3)]
        with self.assertRaisesRegex(ExperimentError, "0.2"):
            analyse(self.config, damaged, AXES)

    def test_restart_or_stream_identity_change_is_rejected(self):
        for change in ("restart", "identity"):
            with self.subTest(change=change):
                damaged = [dict(row) for row in self.rows]
                row = next(r for r in damaged if r["slot"] == "A" and float(r["arrival_s"]) == 7)
                parts = row["line"].split(",")
                if change == "restart":
                    parts[2], parts[3] = "0", "0"
                else:
                    parts[1] = "another_device"
                row["line"] = ",".join(parts)
                with self.assertRaises(ExperimentError):
                    analyse(self.config, damaged, AXES)

    def test_moving_during_initial_calibration_is_rejected(self):
        damaged = [dict(row) for row in self.rows]
        row = next(r for r in damaged if r["slot"] == "A" and float(r["arrival_s"]) == 1)
        parts = row["line"].split(",")
        parts[8] = "20"
        row["line"] = ",".join(parts)
        with self.assertRaisesRegex(ExperimentError, "初始静置"):
            analyse(self.config, damaged, AXES)


class PresetCliTests(unittest.TestCase):
    def test_demo_replay_preserves_source_settings_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp:
            first, second = Path(temp)/"first", Path(temp)/"second"
            self.assertEqual(main(["--demo", "--duration", "8", "--output", str(first)]), 0)
            before = {p.name: p.read_bytes() for p in first.iterdir()}
            self.assertEqual(main(["--demo", "--output", str(first)]), 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in first.iterdir()})
            self.assertEqual(main(["--replay", str(first/"raw.csv"), "--output", str(second)]), 0)
            summary = json.loads((second/"summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["original_source_kind"], "synthetic_demo")
            self.assertEqual(summary["validation_status"], "software_demo_only")
            self.assertAlmostEqual(summary["metrics"]["elbow"]["max_deg"], 90, delta=.4)
            self.assertIn("合成演示数据", (second/"report.html").read_text(encoding="utf-8"))

    def test_placeholder_or_duplicate_endpoint_cannot_open_network(self):
        with self.assertRaises(ExperimentError):
            load_settings("upper_limb", ROOT/"presets"/"endpoints.example.json")
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp:
            p = Path(temp)/"endpoints.json"
            p.write_text(json.dumps({"nodes": {s: {"host": "127.0.0.1"} for s in "ABC"}}), encoding="utf-8")
            with self.assertRaisesRegex(ExperimentError, "必须不同"):
                load_settings("upper_limb", p)


class PresetTcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_simulated_streams_reassemble_fragmented_frames_and_close(self):
        writers, feeders = [], []
        line = b"IMU2,same_id,0,10000,3,0,0,1,0,0,0,25,30,0,10,0\n"

        class Writer:
            closed = False

            def close(self):
                self.closed = True

            async def wait_closed(self):
                return

        async def connection(host, port):
            reader, writer = asyncio.StreamReader(), Writer()
            writers.append(writer)

            async def feed():
                reader.feed_data(line[:14])
                await asyncio.sleep(.002)
                reader.feed_data(line[14:]+line)

            feeders.append(asyncio.create_task(feed()))
            return reader, writer

        with patch("motion_presets.sources.asyncio.open_connection", side_effect=connection):
            endpoints = [("simulated-A", 9000), ("simulated-B", 9000), ("simulated-C", 9000)]
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=RAW_FIELDS)
            rows = await asyncio.wait_for(capture_tcp(endpoints, .12, writer, on_progress=lambda _: None), 4)
            self.assertEqual(len(rows), 6)
            self.assertEqual({row["slot"] for row in rows}, {"A", "B", "C"})
            self.assertTrue(all(row["line"].startswith("IMU2,same_id") for row in rows))
            self.assertTrue(all(w.closed for w in writers))
            await asyncio.gather(*feeders)


if __name__ == "__main__":
    unittest.main()
