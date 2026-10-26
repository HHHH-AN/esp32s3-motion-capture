"""Small numerical checks of the two-pose transform; no devices or scenes."""
import unittest
from copy import deepcopy
from math import sin
from dashboard.body_engine import BodyEngine
from dashboard.body_math import IDENTITY, angle_degrees, inverse, multiply, quaternion, rotate
from dashboard.direction_calibration import CalibrationError, fit_static_direction, summarize_neutral
from tests.direction_fixtures import MountCase, axis_angle, feed, fusion_factory, make_frame


class StaticDirectionMathTests(unittest.TestCase):
    def window(self, rotation, start):
        c = quaternion((.7, .2, -.4, .5))
        f = quaternion((.4, .1, .3, .85))
        q = multiply(f, multiply(rotation, c))
        gravity = rotate((0, 0, 1), inverse(multiply(rotation, c)))
        return [{"time": start+i*.05, "quaternion": q, "accel": gravity, "gyro": (0, 0, 0)} for i in range(21)]

    def test_signed_transform_and_independent_side_direction(self):
        result = fit_static_direction(self.window(IDENTITY, 0), self.window((.866025403784, 0, -.5, 0), 2))
        self.assertEqual(result["algorithm_version"], "gravity-two-static-poses/3")
        self.assertFalse(result["quality"]["intermediate_path_observed"])
        for r in (IDENTITY, quaternion((.9, 0, -.3, 0)), quaternion((.9, -.3, 0, 0))):
            q = self.window(r, 4)[0]["quaternion"]
            actual = multiply(result["fusion_to_world"], multiply(q, result["mount_bone_to_sensor"]))
            self.assertLess(angle_degrees(actual, r), 1e-5)
        self.assertLess(rotate((0, 0, -1), quaternion((.9, -.3, 0, 0)))[1], 0)

    def test_single_pose_or_gravity_axis_cannot_calibrate(self):
        for q in (IDENTITY, quaternion((.9, 0, 0, .3))):
            with self.assertRaises(CalibrationError):
                fit_static_direction(self.window(IDENTITY, 0), self.window(q, 2))

    def test_forward_must_be_stationary(self):
        forward = self.window((.866025403784, 0, -.5, 0), 2)
        for sample in forward:
            sample["gyro"] = (10, 0, 0)
        with self.assertRaisesRegex(CalibrationError, "前举.*停稳"):
            fit_static_direction(self.window(IDENTITY, 0), forward)

    def test_small_sway_and_isolated_spike_are_tolerated_and_reported(self):
        neutral = self.window(IDENTITY, 0)
        forward = self.window((.866025403784, 0, -.5, 0), 2)
        for samples in (neutral, forward):
            for i, sample in enumerate(samples):
                sample["quaternion"] = multiply(sample["quaternion"], axis_angle((1, 0, 0), .4*sin(i)))
                sample["gyro"] = (1.5*sin(i), 0, 0)
            samples[5]["gyro"] = (14, 0, 0)
        original = deepcopy(forward)
        result = fit_static_direction(neutral, forward)
        self.assertEqual(result["quality"]["forward"]["excluded_samples"], 1)
        self.assertEqual(result["quality"]["forward"]["input_samples"], 21)
        self.assertEqual(forward, original)
        # Historical full-motion analysis keeps its strict stationary rule.
        with self.assertRaises(CalibrationError):
            summarize_neutral(neutral)

    def test_sustained_motion_and_large_spike_still_fail(self):
        for speed in (4., 20.):
            forward = self.window((.866025403784, 0, -.5, 0), 2)
            for sample in forward:
                sample["gyro"] = (speed, 0, 0)
            with self.assertRaises(CalibrationError):
                fit_static_direction(self.window(IDENTITY, 0), forward)

    def test_balanced_natural_sway_above_old_single_frame_limit_passes(self):
        forward = self.window((.866025403784, 0, -.5, 0), 2)
        for i, sample in enumerate(forward):
            sample["gyro"] = (5*sin(i), 0, 0)
            sample["quaternion"] = multiply(sample["quaternion"],axis_angle((1,0,0),.4*sin(i)))
        result = fit_static_direction(self.window(IDENTITY, 0), forward)
        self.assertGreater(result["quality"]["forward"]["residual_gyro_peak_dps"], 3.)
        self.assertLess(result["quality"]["forward"]["residual_gyro_mean_dps"], 3.)

    def test_one_large_spike_and_excessive_outliers_are_not_hidden(self):
        for indices, speed in (((5,), 20.), ((5, 10), 14.)):
            forward = self.window((.866025403784, 0, -.5, 0), 2)
            for i in indices:
                forward[i]["gyro"] = (speed, 0, 0)
            with self.assertRaises(CalibrationError):
                fit_static_direction(self.window(IDENTITY, 0), forward)

    def test_handheld_sway_near_ten_dps_with_small_pose_spread_passes(self):
        forward = self.window((.866025403784, 0, -.5, 0), 2)
        for i, sample in enumerate(forward):
            sample["gyro"] = (9.5*sin(i), 0, 0)
            sample["quaternion"] = multiply(sample["quaternion"],axis_angle((1,0,0),.55*sin(i)))
        quality = fit_static_direction(self.window(IDENTITY, 0), forward)["quality"]["forward"]
        self.assertGreater(quality["residual_gyro_peak_dps"], 9.)
        self.assertLess(quality["residual_gyro_mean_dps"], 1.)
        self.assertEqual(quality["excluded_samples"], 0)

    def test_steady_ten_dps_rotation_is_not_handheld_sway(self):
        forward = self.window((.866025403784, 0, -.5, 0), 2)
        for sample in forward:
            sample["gyro"] = (10., 0, 0)
        with self.assertRaises(CalibrationError):
            fit_static_direction(self.window(IDENTITY, 0), forward)

    def test_bad_frame_or_identity_cannot_be_trimmed_as_an_outlier(self):
        for field, value in (("sensor_flags", 0), ("boot_id", "changed")):
            forward = self.window((.866025403784, 0, -.5, 0), 2)
            for sample in forward:
                sample["boot_id"] = "original"
            forward[5].update({field: value, "gyro": (10, 0, 0)})
            with self.assertRaises(CalibrationError):
                fit_static_direction(self.window(IDENTITY, 0), forward)


class HandDirectionScopeTests(unittest.TestCase):
    def test_forearm_and_hand_calibrate_together_and_keep_independent_wrist_motion(self):
        table = {}
        engine = BodyEngine(fusion_factory=fusion_factory(table))
        cases = [MountCase("fixture-forearm", "right_forearm", axis_angle((1, 2, 3), 67), axis_angle((0, 0, 1), 113)),
                 MountCase("fixture-hand", "right_hand", axis_angle((0, 1, 0), 180), axis_angle((0, 0, 1), -71))]
        now, sequence = 100., 0

        def put(forearm=IDENTITY, hand=IDENTITY, moving=False):
            for case, pose in zip(cases, (forearm, hand)):
                frame = make_frame(case, pose, now, sequence,
                                   angular_world=(20., 0., 0.) if moving else (0., 0., 0.))
                feed(engine, table, [frame])

        def capture(pose):
            nonlocal now, sequence
            for _ in range(360):
                now += .01
                sequence += 1
                put(pose, pose)
                engine.snapshot(now)

        put()
        engine.direction_start("neutral", [case.device_id for case in cases], now=now)
        capture(IDENTITY)
        self.assertEqual(engine.direction.state["status"], "neutral_ready")
        engine.direction_start("forward", now=now)
        capture(axis_angle((0, -1, 0), 60))
        self.assertEqual(engine.direction.state["status"], "candidate")
        engine.direction_apply(now=now)
        references = {case.device_id: engine.devices[case.device_id].reference for case in cases}
        engine.direction_cancel()
        for case in cases:
            node = engine.devices[case.device_id]
            self.assertTrue(node.direction_calibration["valid"], "ending the capture scope must retain applied transforms")
            self.assertEqual(node.reference, references[case.device_id])

        forearm = axis_angle((0, -1, 0), 35)
        wrist = axis_angle((1, 0, 0), 25)
        hand = multiply(forearm, wrist)
        now += .01
        sequence += 1
        put(forearm, hand, moving=True)
        frame = engine.snapshot(now+.081)["body_frame"]
        segments = {segment["id"]: segment for segment in frame["segments"]}
        self.assertLess(angle_degrees(segments["right_forearm"]["world_quaternion"], forearm), 1e-5)
        self.assertLess(angle_degrees(segments["right_hand"]["world_quaternion"], hand), 1e-5)
        self.assertLess(angle_degrees(segments["right_hand"]["local_quaternion"], wrist), 1e-5)


class StableCaptureTests(unittest.TestCase):
    def setUp(self):
        self.table = {}
        self.engine = BodyEngine(fusion_factory=fusion_factory(self.table))
        self.case = MountCase("stable-arm", "right_upper_arm")
        self.seq = 0
        self.now = 100.
        self.put()

    def put(self, speed=0., angle=0.):
        frame = make_frame(self.case, axis_angle((0, -1, 0), angle), self.now, self.seq,
                           angular_world=(speed, 0, 0))
        feed(self.engine, self.table, [frame])
        self.seq += 1

    def advance(self, seconds, speed=0., angle=0.):
        for _ in range(round(seconds*100)):
            self.now += .01
            self.put(speed, angle)
            self.engine.snapshot(self.now)

    def test_preparation_then_automatic_retry_without_reclicking(self):
        self.engine.direction_start("neutral", [self.case.device_id], now=self.now)
        self.advance(2.5, speed=8.)
        self.assertEqual(self.engine.direction.state["status"], "capturing")
        self.advance(1., speed=8.)
        self.assertEqual(self.engine.direction.state["status"], "capturing")
        self.assertTrue(self.engine.direction.state["waiting_reason"])
        self.advance(1.7)
        self.assertEqual(self.engine.direction.state["status"], "neutral_ready")
        self.assertIsNone(self.engine.devices[self.case.device_id].reference)
        self.engine.direction_start("forward", now=self.now)
        self.advance(2., speed=10., angle=60.)
        self.advance(1.7, angle=60.)
        self.assertEqual(self.engine.direction.state["status"], "candidate")
        self.assertIsNone(self.engine.devices[self.case.device_id].reference)
        self.assertTrue(self.engine.direction.evidence_snapshot()["selected_windows"]["forward"])

    def test_no_stable_window_times_out_with_measurement_reason(self):
        self.engine.direction_start("neutral", [self.case.device_id], now=self.now)
        self.advance(15.2, speed=8.)
        self.assertEqual(self.engine.direction.state["status"], "failed")
        self.assertIn("角速度", self.engine.direction.state["message"])
        self.assertIn("超时", self.engine.direction.state["message"])

    def test_disconnect_during_wait_still_fails_immediately(self):
        self.engine.direction_start("neutral", [self.case.device_id], now=self.now)
        self.advance(.5)
        self.engine.disconnect_endpoint("fixture-"+self.case.device_id)
        self.engine.snapshot(self.now)
        self.assertEqual(self.engine.direction.state["status"], "failed")

    def test_devices_must_be_stable_in_the_same_window(self):
        other = MountCase("stable-forearm", "right_forearm")
        feed(self.engine, self.table, [make_frame(other,time_s=self.now,seq=0)])
        self.engine.direction_start("neutral", [self.case.device_id,other.device_id], now=self.now)
        for i in range(600):
            self.now += .01
            # Each board gets a stable interval, but these do not overlap.
            self.put(speed=8. if i < 400 else 0.)
            feed(self.engine,self.table,[make_frame(other,time_s=self.now,seq=i+1,
                                                   angular_world=(0. if i < 400 else 8.,0,0))])
            self.engine.snapshot(self.now)
        self.assertEqual(self.engine.direction.state["status"], "capturing")
        self.assertFalse(self.engine.direction.neutral_valid)

    def test_bad_frame_and_missing_sequence_are_not_retried_as_motion(self):
        for error in ("bad_frame", "missing_sequence"):
            with self.subTest(error=error):
                self.setUp()
                self.engine.direction_start("neutral", [self.case.device_id], now=self.now)
                self.advance(.5)
                if error == "bad_frame":
                    self.engine.invalid_frame("fixture-"+self.case.device_id,"bad")
                else:
                    self.seq += 1
                    self.now += .01
                    self.put()
                self.engine.snapshot(self.now)
                self.assertEqual(self.engine.direction.state["status"], "failed")

    def test_manual_finish_cannot_bypass_preparation(self):
        self.engine.direction_start("neutral", [self.case.device_id], now=self.now)
        self.advance(1.4)
        state = self.engine.direction_finish(now=self.now)
        self.assertEqual(state["status"], "failed")
        self.assertFalse(self.engine.direction.neutral_valid)
