"""Saved-frame fidelity and fail-closed recording, entirely without hardware."""
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from dashboard.body_recording import BodyRecorder, BodyReplay, catalog, session_path


class BodyRecordingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_recording(self, count=8):
        recorder = BodyRecorder(self.root)
        session = recorder.start({"config": {"skeleton_version": "neutral/1"},
                                  "bindings": {"physical_a": "left_hand"}})
        for i in range(count):
            recorder.append("body_frames", {"number": i, "q": [1., 0., 0., 0.],
                                           "source": "simulation_pose"}, elapsed=i*.01)
        recorder.stop()
        return session

    def test_more_than_5000_frames_replay_without_decimation(self):
        session = self.make_recording(6201)
        lines = (self.root / session / "body_frames.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 6201)
        replay = BodyReplay(self.root)
        self.addCleanup(replay.close)
        replay.open(session)
        self.assertEqual(replay.frame()["number"], 0)
        self.assertEqual(replay.seek(56.007)["number"], 5600)
        self.assertEqual(replay.seek(23.457)["number"], 2345)
        self.assertEqual(replay.seek(1e6)["number"], 6200)
        self.assertEqual(replay.seek(-1)["number"], 0)
        self.assertAlmostEqual(replay.duration, 62.0)
        self.assertGreater(len(replay.index), 40)
        self.assertEqual(catalog(self.root)[0]["counts"]["body_frames"], 6201)

    def test_metadata_and_sample_payload_are_snapshots(self):
        snapshot = {"config": {"lengths": [0.3, 0.4]}, "calibration": {"id": "original"}}
        recorder = BodyRecorder(self.root)
        session = recorder.start(snapshot)
        snapshot["config"]["lengths"][0] = 9.0
        snapshot["calibration"]["id"] = "changed"
        sample = {"source": "simulation_sensor", "device_id": "device_a", "raw": [1, 2, 3]}
        self.assertTrue(recorder.append_sample(sample))
        sample["raw"][0] = 99
        body = {"segments": [{"quaternion": [1, 0, 0, 0]}]}
        recorder.append_body_frame(body)
        body["segments"][0]["quaternion"][0] = 0
        recorder.stop()
        metadata = json.loads((self.root / session / "metadata.json").read_text())
        self.assertEqual(metadata["snapshot"]["config"]["lengths"], [0.3, 0.4])
        self.assertEqual(metadata["snapshot"]["calibration"]["id"], "original")
        self.assertEqual(metadata["source_types"], ["simulation_sensor"])
        self.assertEqual(metadata["status"], "complete")
        samples = [json.loads(line)["data"] for line in (self.root/session/"samples.jsonl").read_text().splitlines()]
        self.assertEqual(samples[0]["raw"], [1, 2, 3])
        replay = BodyReplay(self.root)
        self.addCleanup(replay.close)
        replay.open(session)
        displayed = replay.frame()
        displayed["segments"][0]["quaternion"][0] = 9
        self.assertEqual(replay.frame()["segments"][0]["quaternion"], [1, 0, 0, 0])

    def test_play_pause_seek_uses_saved_frames_without_fusion(self):
        session = self.make_recording(20)
        replay = BodyReplay(self.root)
        self.addCleanup(replay.close)
        replay.open(session)
        with patch("dashboard.body_recording.monotonic", return_value=100.):
            replay.play()
        with patch("dashboard.body_recording.monotonic", return_value=100.115):
            self.assertEqual(replay.advance()["number"], 11)
        replay.playing = False
        with patch("dashboard.body_recording.monotonic", return_value=1000):
            self.assertEqual(replay.advance()["number"], 11)
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                replay.seek(value)
        self.assertEqual(replay.seek(.057)["number"], 5)
        replay.close()
        self.assertIsNone(replay.frame())
        self.assertFalse(replay.playing)

    def test_overload_stops_and_marks_incomplete_without_silent_drops(self):
        recorder = BodyRecorder(self.root, capacity=2)
        release = Event()
        original = recorder._write

        def delayed_worker():
            release.wait(3)
            original()

        recorder._write = delayed_worker
        session = recorder.start({})
        try:
            self.assertTrue(recorder.append_sample({"value": "accepted"}))
            self.assertFalse(recorder.append_body_frame({"value": "overflow"}))
            self.assertFalse(recorder.active)
            self.assertIsNotNone(recorder.error)
        finally:
            release.set()
            recorder.stop()
        meta = json.loads((self.root/session/"metadata.json").read_text())
        self.assertEqual(meta["status"], "incomplete")
        self.assertEqual(meta["counts"]["samples"], 1)
        self.assertEqual(meta["counts"]["body_frames"], 0)
        self.assertFalse(recorder.append_sample({}))

    def test_cannot_restart_failed_recorder_until_old_worker_is_finalized(self):
        recorder = BodyRecorder(self.root, capacity=1)
        release = Event()
        original = recorder._write

        def delayed_worker():
            release.wait(3)
            original()

        recorder._write = delayed_worker
        first = recorder.start({})
        recorder.append_sample({"overflow": True})
        try:
            with self.assertRaises(ValueError):
                recorder.start({})
            self.assertEqual(recorder.session, first)
        finally:
            release.set()
            recorder.stop()

    def test_disk_write_failure_stops_and_preserves_incomplete_metadata(self):
        recorder = BodyRecorder(self.root)
        failed = Event()
        original_open = Path.open

        class BrokenWriter:
            def write(self, data):
                failed.set()
                raise OSError("simulated disk full")
            def close(self):
                pass

        def patched_open(path, *args, **kwargs):
            if path.name == "samples.jsonl" and args and args[0] == "wb":
                return BrokenWriter()
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", patched_open):
            session = recorder.start({})
            recorder.append_sample({"source": "simulation_sensor"})
            self.assertTrue(failed.wait(2))
            recorder.stop()
        self.assertFalse(recorder.active)
        self.assertIn("simulated disk full", recorder.error)
        meta = json.loads((self.root/session/"metadata.json").read_text())
        self.assertEqual(meta["status"], "incomplete")

    def test_buffer_close_failure_is_not_marked_complete(self):
        recorder = BodyRecorder(self.root)
        original_open = Path.open

        class CloseFailure:
            def write(self, data):
                return len(data)
            def close(self):
                raise OSError("simulated flush failure")

        def patched_open(path, *args, **kwargs):
            if path.name == "samples.jsonl" and args and args[0] == "wb":
                return CloseFailure()
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", patched_open):
            session = recorder.start({})
            recorder.append_sample({"source": "simulation_sensor"})
            recorder.stop()
        self.assertFalse(recorder.active)
        self.assertIn("simulated flush failure", recorder.error)
        meta = json.loads((self.root/session/"metadata.json").read_text())
        self.assertEqual(meta["status"], "incomplete")

    def test_corrupt_index_does_not_leave_loaded_or_open_session(self):
        session = self.make_recording()
        (self.root/session/"frame_index.jsonl").write_text("{not valid json\n")
        replay = BodyReplay(self.root)
        self.addCleanup(replay.close)
        with self.assertRaises(ValueError):
            replay.open(session)
        self.assertIsNone(replay.session)
        self.assertIsNone(replay._handle)
        self.assertEqual(replay.duration, 0)

    def test_session_traversal_and_empty_records_are_rejected(self):
        for name in ("..", "../not-a-session", "", "C:\\Windows"):
            with self.assertRaises(ValueError):
                session_path(self.root, name)
        recorder = BodyRecorder(self.root)
        session = recorder.start({})
        recorder.stop()
        replay = BodyReplay(self.root)
        self.addCleanup(replay.close)
        with self.assertRaises(ValueError):
            replay.open(session)


if __name__ == "__main__":
    unittest.main()
