"""Regression tests for position runaway after an IMU has actually stopped.

The samples below are synthetic: they test estimator logic, not real-world
position accuracy or the unobservable distinction between rest and constant
linear velocity.  No sensor-bias implementation details are assumed.
"""

import math
import unittest

from dashboard.coordinates import CoordinateSettings
from dashboard.fusion import ComplementaryFusion, euler_quaternion
from dashboard.kinematics import rotate
from dashboard.models import SensorSample
from dashboard.motion import DisplacementEstimator


def norm(vector):
    return math.sqrt(sum(value * value for value in vector))


def observation(index, rate=100, accel=(0, 0, 1), gyro=(0, 0, 0), base=0):
    return SensorSample(
        accel, gyro, (30, 0, 10), 25, 0,
        received_monotonic=base + index / rate,
        device_us=round(index * 1_000_000 / rate),
        sequence=index,
    )


def initialize_motion(rate=100, quaternion=(1, 0, 0, 0)):
    motion = DisplacementEstimator()
    motion.start(0, True, "balanced")
    index = 0
    while index < math.ceil(1.2 * rate):
        motion.update(observation(index, rate), quaternion)
        index += 1
    if motion.phase != "measuring":
        raise AssertionError("Ideal static baseline did not initialize")
    return motion, index


class StopLockRegressionTests(unittest.TestCase):
    def test_magnetic_heading_uses_the_same_tilt_convention_as_the_quaternion(self):
        for roll, pitch, yaw in (
            (30, 30, 0), (45, 45, 0), (60, 20, 90),
            (-30, 40, -90), (70, -60, 179), (-70, -50, -179),
            (0, 80, 45), (179, 0, -45), (90, 45, 135),
        ):
            with self.subTest(roll=roll, pitch=pitch, yaw=yaw):
                expected = euler_quaternion(*(math.radians(value) for value in (roll, pitch, yaw)))
                inverse = (expected[0], -expected[1], -expected[2], -expected[3])
                # Generate both instruments from one known body-to-world pose.
                accel_body = rotate((0, 0, 1), inverse)
                magnetic_body = rotate((30, 0, 10), inverse)
                sample = observation(0, accel=accel_body)
                sample.mag = magnetic_body
                observed = ComplementaryFusion().update(sample)
                agreement = abs(sum(a * b for a, b in zip(expected, observed)))
                self.assertAlmostEqual(agreement, 1, places=7)

    def test_stopped_fusion_and_motion_recover_from_two_degree_tilt_error(self):
        motion, index = initialize_motion()
        fusion = ComplementaryFusion()
        fusion.update(observation(index - 1))
        # A modest fusion error can remain after a preceding movement.  The
        # next ten seconds contain exactly stationary raw IMU measurements.
        fusion.q = euler_quaternion(0, math.radians(2), 0)
        for offset in range(1000):
            sample = observation(index + offset)
            # The public fusion/motion APIs reproduce Runtime's adaptive gain
            # contract without opening an event loop or any transport sockets.
            gain = 1 if motion.stationary else .05
            motion.update(sample, fusion.update(sample, correction_scale=gain))
            if offset == 499:
                held_position = motion.position

        payload = motion.payload(CoordinateSettings())
        self.assertEqual(payload["quality"], "stationary_constraint")
        self.assertTrue(payload["stationary"])
        self.assertEqual(tuple(payload["velocity"]), (0, 0, 0))
        self.assertEqual(motion.position, held_position)
        self.assertLess(norm(payload["position"]), .1)

    def test_initial_tilt_error_does_not_become_permanent_horizontal_bias(self):
        wrong_quaternion = euler_quaternion(0, math.radians(2), 0)
        motion, index = initialize_motion(quaternion=wrong_quaternion)

        # Restoring the exact attitude must not expose a fictitious learned
        # horizontal accelerometer bias which then defeats the stationary gate.
        for offset in range(500):
            motion.update(observation(index + offset), (1, 0, 0, 0))
        held_position = motion.position
        for offset in range(500, 1000):
            motion.update(observation(index + offset), (1, 0, 0, 0))

        payload = motion.payload(CoordinateSettings())
        self.assertEqual(payload["quality"], "stationary_constraint")
        self.assertEqual(tuple(payload["velocity"]), (0, 0, 0))
        self.assertEqual(motion.position, held_position)
        self.assertLess(norm(payload["position"]), .05)

    def test_stop_lock_timing_is_time_based_at_25_50_and_100_hz(self):
        for rate in (25, 50, 100):
            with self.subTest(rate=rate):
                motion, index = initialize_motion(rate)
                for _ in range(rate):
                    motion.update(observation(index, rate, (.2, 0, 1), (10, 0, 0)), (1, 0, 0, 0))
                    index += 1
                self.assertNotEqual(motion.payload(CoordinateSettings())["quality"], "stationary_constraint")

                locked_after = None
                for offset in range(math.ceil(.6 * rate)):
                    motion.update(observation(index, rate), (1, 0, 0, 0))
                    index += 1
                    if motion.payload(CoordinateSettings())["quality"] == "stationary_constraint":
                        locked_after = (offset + 1) / rate
                        break
                self.assertIsNotNone(locked_after, "A real stop was never locked")
                self.assertLessEqual(locked_after, .5 + 1 / rate)
                self.assertEqual(motion.velocity, (0, 0, 0))

                held_position = motion.position
                for _ in range(2 * rate):
                    motion.update(observation(index, rate), (1, 0, 0, 0))
                    index += 1
                self.assertEqual(motion.position, held_position)

    def test_obvious_rotation_is_not_stationary(self):
        motion, index = initialize_motion()
        for offset in range(200):
            quaternion = euler_quaternion(math.radians(30) * offset / 100, 0, 0)
            angle = math.radians(30) * offset / 100
            accel = (0, math.sin(angle), math.cos(angle))
            motion.update(observation(index + offset, accel=accel, gyro=(30, 0, 0)), quaternion)
            self.assertFalse(motion.stationary)
            self.assertNotEqual(motion.payload(CoordinateSettings())["quality"], "stationary_constraint")

    def test_obvious_vibration_is_not_stationary(self):
        motion, index = initialize_motion()
        for offset in range(200):
            accel = (.08 if offset % 2 == 0 else -.08, 0, 1)
            motion.update(observation(index + offset, accel=accel), (1, 0, 0, 0))
            self.assertFalse(motion.stationary)
            self.assertNotEqual(motion.payload(CoordinateSettings())["quality"], "stationary_constraint")


if __name__ == "__main__":
    unittest.main()
