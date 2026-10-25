"""Geometric invariants and independent-node failure paths, without hardware."""
from copy import deepcopy
from dataclasses import replace
import math
import unittest

from dashboard.body_config import canonical_slot, load_config, validate_config
from dashboard.body_engine import BodyEngine
from dashboard.body_math import IDENTITY, angle_degrees, mean, multiply, quaternion, rotate, slerp
from dashboard.fusion import euler_quaternion
from dashboard.models import SensorSample


def sample(device="board_A", slot=None, seq=0, now=100., boot="boot1", gyro=(0., 0., 0.), **kwargs):
    return SensorSample((0., 0., 1.), gyro, (300., 0., 80.), 25., 0.,
                        received_monotonic=now, received_unix=now+100000,
                        node_id=device, sequence=seq, device_us=(seq*10000) % 2**32,
                        body_slot=slot, boot_id=boot, firmware_version="fw1", config_version="cfg1",
                        protocol_version="IMU3", **kwargs)


def segment(snapshot, slot):
    return next(s for s in snapshot["body_frame"]["segments"] if s["id"] == slot)


class BodyMathTests(unittest.TestCase):
    def test_noncommuting_rotations_and_slerp(self):
        x = euler_quaternion(math.pi/2, 0., 0.)
        z = euler_quaternion(0., 0., math.pi/2)
        self.assertGreater(angle_degrees(multiply(x, z), multiply(z, x)), 100)
        self.assertAlmostEqual(angle_degrees(IDENTITY, slerp(IDENTITY, z, .5)), 45.)
        self.assertLess(angle_degrees(mean([z, tuple(-v for v in z)]), z), 1e-6)

    def test_invalid_rotations_are_rejected(self):
        for value in ((0, 0, 0, 0), (float("nan"), 0, 0, 0), (1, 2), (1, True, 0, 0)):
            with self.assertRaises(ValueError):
                quaternion(value)


class BodyConfigurationTests(unittest.TestCase):
    def test_fourteen_slots_aliases_require_explicit_versioned_mapping(self):
        config = load_config()
        self.assertEqual(len(config["segments"]), 14)
        with self.assertRaises(ValueError):
            canonical_slot(config, "right_wrist")
        self.assertEqual(canonical_slot(config, "right_wrist", allow_alias=True), "right_hand")

    def test_layout_rejects_cycle_and_invalid_lengths(self):
        config = load_config()
        config["segments"][0]["parent"] = "head"
        with self.assertRaises(ValueError):
            validate_config(config)
        config = load_config()
        config["segments"][0]["length"] = float("nan")
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_default_neutral_arms_down_feet_forward_and_lengths_configurable(self):
        engine = BodyEngine()
        frame = engine.snapshot(100.)
        upper = segment(frame, "left_upper_arm")
        self.assertAlmostEqual(upper["start"][0], upper["end"][0])
        self.assertLess(upper["end"][2], upper["start"][2])
        foot = segment(frame, "left_foot")
        self.assertGreater(foot["end"][0], foot["start"][0])
        changed = deepcopy(engine.config)
        next(s for s in changed["segments"] if s["id"] == "left_upper_arm")["length"] = .6
        extended = BodyEngine(changed).snapshot(100.)
        self.assertAlmostEqual(segment(extended, "left_forearm")["start"][2], upper["start"][2]-.6)
        self.assertTrue(all(not s["measured"] and s["local_quaternion"] == IDENTITY for s in frame["body_frame"]["segments"]))


class BodySolverTests(unittest.TestCase):
    def test_one_parent_moves_unmeasured_children_without_extra_local_rotation(self):
        engine = BodyEngine()
        q = euler_quaternion(math.pi/2, 0., 0.)
        engine.ingest_pose("upper", "left_upper_arm", q, now=100.)
        body = engine.snapshot(100.)
        forearm = segment(body, "left_forearm")
        hand = segment(body, "left_hand")
        self.assertEqual(forearm["local_quaternion"], IDENTITY)
        self.assertLess(angle_degrees(forearm["world_quaternion"], q), 1e-6)
        self.assertLess(angle_degrees(hand["world_quaternion"], q), 1e-6)
        self.assertFalse(forearm["measured"])
        self.assertEqual(segment(body, "right_upper_arm")["world_quaternion"], IDENTITY)
        self.assertEqual(body["body_frame"]["real_online"], 0)
        self.assertEqual(body["body_frame"]["simulation_online"], 1)

    def test_measured_world_rotations_are_not_applied_twice(self):
        engine = BodyEngine()
        q = euler_quaternion(0., math.pi/3, math.pi/5)
        engine.ingest_pose("root", "pelvis", q, now=100.)
        engine.ingest_pose("upper", "left_upper_arm", q, now=100.)
        engine.ingest_pose("forearm", "left_forearm", q, now=100.)
        body = engine.snapshot(100.)
        self.assertLess(angle_degrees(segment(body, "left_upper_arm")["local_quaternion"], IDENTITY), 1e-6)
        self.assertLess(angle_degrees(segment(body, "left_forearm")["world_quaternion"], q), 1e-6)
        for s in body["body_frame"]["segments"]:
            distance = math.sqrt(sum((b-a)**2 for a, b in zip(s["start"], s["end"])))
            self.assertAlmostEqual(distance, s["length"], places=10)

    def test_hand_only_does_not_invent_arm_movement(self):
        engine = BodyEngine()
        engine.ingest_pose("hand", "right_hand", euler_quaternion(.8, .4, .2), now=100.)
        body = engine.snapshot(100.)
        self.assertEqual(segment(body, "right_upper_arm")["world_quaternion"], IDENTITY)
        self.assertEqual(segment(body, "right_forearm")["world_quaternion"], IDENTITY)
        self.assertTrue(segment(body, "right_hand")["chain_degraded"])
        self.assertEqual(sum(s["measured"] for s in body["body_frame"]["segments"]), 1)

    def test_stale_node_holds_last_local_with_parent_following(self):
        engine = BodyEngine()
        qchild = euler_quaternion(.3, .5, .1)
        engine.ingest_pose("child", "left_forearm", qchild, now=100.)
        engine.snapshot(100.)
        qparent = euler_quaternion(.5, 0., 0.)
        engine.ingest_pose("parent", "left_upper_arm", qparent, now=102.)
        body = engine.snapshot(102.)
        child = segment(body, "left_forearm")
        self.assertEqual(child["status"], "stale")
        self.assertFalse(child["measured"])
        self.assertLess(angle_degrees(child["local_quaternion"], qchild), 1e-6)
        self.assertLess(angle_degrees(child["world_quaternion"], multiply(qparent, qchild)), 1e-6)

    def test_conflicting_devices_are_both_quarantined(self):
        engine = BodyEngine()
        engine.ingest_pose("A", "head", euler_quaternion(.5, 0, 0), now=100.)
        engine.ingest_pose("B", "head", euler_quaternion(0, .5, 0), now=100.)
        body = engine.snapshot(100.)
        head = segment(body, "head")
        self.assertEqual(head["status"], "conflict")
        self.assertFalse(head["measured"])
        self.assertEqual(head["local_quaternion"], IDENTITY)
        self.assertTrue(all(not d["initialized"] for d in body["devices"]))
        self.assertIn("slot_conflict", [e["type"] for e in engine.pop_events()])


class DeviceProcessingTests(unittest.TestCase):
    def test_fusion_clock_and_bias_are_independent(self):
        engine = BodyEngine()
        for seq in range(50):
            engine.ingest(sample("A", "head", seq, 100+seq*.01, gyro=(0., 0., 30.)), "tcpA")
            engine.ingest(sample("B", "pelvis", seq, 100+seq*.01), "usbB")
        a, b = engine.devices["A"], engine.devices["B"]
        self.assertIsNot(a.fusion, b.fusion)
        self.assertIsNot(a.stability, b.stability)
        self.assertGreater(angle_degrees(a.quaternion, b.quaternion), 5)
        self.assertEqual((a.valid_frames, b.valid_frames), (50, 50))
        self.assertIsNotNone(a.clock_offset_s)

    def test_legacy_missing_role_does_not_become_right_hand(self):
        engine = BodyEngine()
        old = replace(sample(), sequence=None, device_us=None, boot_id=None, protocol_version="legacy")
        engine.ingest(old, "COM7")
        body = engine.snapshot(100.)
        device = body["devices"][0]
        self.assertEqual(device["device_id"], "legacy:COM7")
        self.assertFalse(device["identity_trusted"])
        self.assertIsNone(device["body_slot"])
        self.assertEqual(sum(s["measured"] for s in body["slots"]), 0)
        engine.bind("legacy:COM7", "right_hand")
        self.assertEqual(engine.devices["legacy:COM7"].body_slot, "right_hand")

    def test_same_device_two_transports_never_integrates_twice(self):
        engine = BodyEngine()
        first = sample("A", "head", seq=1)
        self.assertIsNotNone(engine.ingest(first, "usb"))
        self.assertIsNone(engine.ingest(first, "tcp"))
        self.assertIsNone(engine.ingest(replace(first, sequence=2), "tcp"))
        self.assertEqual(engine.devices["A"].valid_frames, 1)
        self.assertEqual(engine.devices["A"].duplicate_sources, 2)
        self.assertEqual(engine.devices["A"].primary_endpoint, "usb")

    def test_sequence_loss_duplicates_wrap_and_device_microsecond_wrap(self):
        engine = BodyEngine()
        for seq, micros, now in [(2**32-2, 2**32-15000, 100.), (2**32-1, 2**32-5000, 100.01),
                                  (0, 5000, 100.02), (3, 35000, 100.05), (3, 35000, 100.06)]:
            engine.ingest(replace(sample("A", "head", seq=seq, now=now), device_us=micros), "tcp")
        node = engine.devices["A"]
        self.assertEqual(node.valid_frames, 4)
        self.assertEqual(node.missing_frames, 2)
        self.assertEqual(node.duplicates, 1)
        self.assertEqual(node.restarts, 0)
        self.assertEqual(node.unwrapped_device_us, 2**32+35000)

    def test_boot_reboot_invalidates_reference_and_clears_buffer(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "head", seq=5), "tcp")
        node = engine.devices["A"]
        node.reference = IDENTITY
        engine.ingest(sample("A", "head", seq=0, now=101., boot="boot2"), "tcp")
        self.assertFalse(node.initialized)
        self.assertEqual(node.restarts, 1)
        self.assertEqual(len(node.history), 1)

    def test_unknown_firmware_slot_is_diagnostic_only(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "finger42"), "tcp")
        node = engine.devices["A"]
        self.assertIsNone(node.body_slot)
        self.assertEqual(node.unknown_slot, "finger42")
        self.assertEqual(sum(s["measured"] for s in engine.snapshot(100.)["slots"]), 0)

    def test_binding_override_explicit_and_coordinate_change_invalidate_reference(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "head"), "tcp")
        with self.assertRaises(ValueError):
            engine.bind("A", "right_hand")
        engine.bind("A", "right_hand", override=True)
        node = engine.devices["A"]
        self.assertTrue(node.override)
        node.reference = IDENTITY
        engine.set_coordinates("A", {"sensor_axes": ["-X", "-Y", "+Z"]})
        self.assertFalse(node.initialized)
        engine.clear_override("A")
        self.assertEqual(node.body_slot, "head")

    def test_nonfinite_or_invalid_flags_rejected_and_counted(self):
        engine = BodyEngine()
        for bad in [replace(sample(), gyro=(float("nan"), 0, 0)), replace(sample(), sensor_flags=2)]:
            self.assertIsNone(engine.ingest(bad, "tcp"))
        self.assertEqual(engine.devices["board_A"].invalid_frames, 2)
        self.assertIsNone(engine.devices["board_A"].latest_at)

    def test_changed_physical_identity_on_endpoint_does_not_keep_old_reference(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "head"), "usb")
        engine.devices["A"].reference = IDENTITY
        engine.ingest(sample("B", "left_hand"), "usb")
        self.assertFalse(engine.devices["A"].initialized)
        self.assertFalse(engine.devices["A"].connected)
        self.assertFalse(engine.devices["B"].initialized)

    def test_injected_provider_is_used_and_invalid_output_rejected(self):
        class Provider:
            version = "test-provider/1"
            def update(self, sample, correction_scale=1.):
                return (0.,)*4
            def reset(self):
                pass
        engine = BodyEngine(fusion_factory=Provider)
        self.assertIsNone(engine.ingest(sample("A", "head"), "tcp"))
        self.assertEqual(engine.devices["A"].fusion_version, "test-provider/1")
        self.assertEqual(engine.devices["A"].invalid_frames, 1)


class GuidedInitializationTests(unittest.TestCase):
    def test_confirm_precedes_collection_and_only_selected_nodes_initialize(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "left_hand"), "tcpA")
        engine.ingest(sample("B", "right_hand"), "tcpB")
        engine.begin_initialization(["A"], now=100.)
        for seq in range(1, 111):
            engine.ingest(sample("A", "left_hand", seq=seq, now=100+seq*.01), "tcpA")
        self.assertEqual(engine.snapshot(101.1)["initialization"]["status"], "prepared")
        self.assertFalse(engine.devices["A"].initialized)
        engine.finish_initialization(now=101.1)
        self.assertEqual(engine.initialization["status"], "collecting")
        for seq in range(111, 215):
            engine.ingest(sample("A", "left_hand", seq=seq, now=100+seq*.01), "tcpA")
            engine.ingest(sample("B", "right_hand", seq=seq, now=100+seq*.01), "tcpB")
        body = engine.snapshot(102.14)
        self.assertEqual(body["initialization"]["status"], "complete")
        self.assertTrue(engine.devices["A"].initialized)
        self.assertFalse(engine.devices["B"].initialized)
        self.assertEqual(body["initialization"]["scope"], ["left_hand"])

    def test_moving_sample_fails_initialization(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "head"), "tcp")
        engine.begin_initialization(now=100.)
        engine.finish_initialization(now=100.)
        engine.ingest(sample("A", "head", seq=1, now=100.01, gyro=(10., 0., 0.)), "tcp")
        self.assertEqual(engine.snapshot(100.01)["initialization"]["status"], "failed")
        self.assertFalse(engine.devices["A"].initialized)

    def test_complete_initialization_requires_complete_layout(self):
        engine = BodyEngine()
        engine.ingest(sample("A", "head"), "tcp")
        with self.assertRaises(ValueError):
            engine.begin_initialization(full=True, now=100.)

    def test_fourteen_raw_devices_have_isolated_buffers_and_no_inferred_movements(self):
        engine = BodyEngine()
        for index, spec in enumerate(engine.config["segments"]):
            for seq in range(5):
                engine.ingest(sample(f"node{index}", spec["id"], seq, 100+seq*.01), f"sim{index}", source="simulation_sensor")
        body = engine.snapshot(100.04)
        self.assertEqual(len(body["devices"]), 14)
        self.assertTrue(all(d["quality"]["valid_frames"] == 5 for d in body["devices"]))
        self.assertEqual(body["body_frame"]["real_online"], 0)
        self.assertTrue(all(s["status"] == "uninitialized" for s in body["slots"]))


if __name__ == "__main__":
    unittest.main()
