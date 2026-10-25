"""Optional six-axis gravity correction across vertical Euler branches."""
import math
import unittest

from dashboard.fusion import (ComplementaryFusion, euler_degrees,
                              euler_quaternion, multiply, relative)
from dashboard.models import SensorSample


def gravity_in_body(q):
    w, x, y, z = q
    return (2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y))


def rotation_angle(q):
    return 2*math.degrees(math.acos(min(1., abs(q[0]))))


def sample(index, accel=(0., 0., 1.), gyro=(0., 0., 0.), mag=(0., 0., 0.), flags=1):
    return SensorSample(accel, gyro, mag, 25., 0., received_monotonic=index*.01,
                        device_us=index*10000, sensor_flags=flags)


def noisy_pitch_return(peak_degrees):
    # Same upside-down body frame used by the mapped real board. Small gyro
    # offsets remain deliberately uncalibrated: correction must not amplify
    # these into tens of degrees of heading near vertical pitch.
    for index in range(2401):
        t = index*.01
        if t < 2:
            degrees, rate = 0., 0.
        elif t < 4:
            degrees, rate = peak_degrees*(t-2)/2, peak_degrees/2
        elif t < 14:
            degrees, rate = peak_degrees, 0.
        elif t < 16:
            degrees, rate = peak_degrees*(16-t)/2, -peak_degrees/2
        else:
            degrees, rate = 0., 0.
        truth = multiply(euler_quaternion(math.pi, 0., 0.),
                         euler_quaternion(0., math.radians(degrees), 0.))
        gravity = gravity_in_body(truth)
        accel = (gravity[0]+.002*math.sin(index*.17),
                 gravity[1]+.003*math.sin(index*.29),
                 gravity[2]+.002*math.cos(index*.11))
        gyro = (.1+.03*math.sin(index*.23),
                rate+.12+.03*math.sin(index*.31),
                .03+.03*math.cos(index*.19))
        yield index, sample(index, accel, gyro)


class GravityVectorFusionTests(unittest.TestCase):
    def test_near_vertical_noise_does_not_amplify_small_bias_into_large_heading(self):
        for peak in (88.5, 90., 100.):
            with self.subTest(pitch_degrees=peak):
                stable = ComplementaryFusion(gravity_vector_correction=True)
                legacy = ComplementaryFusion()
                rest_start = rest_end = None
                for index, current in noisy_pitch_return(peak):
                    q = stable.update(current)
                    legacy.update(current)
                    self.assertTrue(all(math.isfinite(value) for value in q))
                    self.assertAlmostEqual(sum(value*value for value in q), 1., places=12)
                    if index == 1100:
                        rest_start = q
                    if index == 1300:
                        rest_end = q
                # The residual uncalibrated gyro bias is allowed to move
                # heading modestly. There is no artificial pose hold.
                self.assertLess(abs(euler_degrees(stable.q)[2]), 1.5)
                self.assertLess(rotation_angle(relative(rest_end, rest_start)), 1.)
                if peak == 88.5:
                    # Preserve a meaningful regression trigger: the default
                    # legacy path remains opt-in compatible and exhibits the
                    # former ~20 degree correction-induced heading change.
                    self.assertGreater(abs(euler_degrees(legacy.q)[2]), 15.)
                    self.assertFalse(legacy.gravity_vector_correction)

    def test_shortest_arc_correction_has_no_world_vertical_rotation_component(self):
        fusion = ComplementaryFusion(gravity_vector_correction=True)
        fusion.q = euler_quaternion(.8, .5, 1.2)
        fusion.last_time, fusion.last_device_us = 0., 0
        predicted = fusion.q
        q = fusion.update(sample(1, accel=(.2, .3, .93)))
        world_delta = multiply(q, (predicted[0], -predicted[1], -predicted[2], -predicted[3]))
        self.assertAlmostEqual(world_delta[3], 0., places=12)
        self.assertGreater(abs(world_delta[1])+abs(world_delta[2]), 0.)

    def test_initialization_still_observes_gravity_with_zero_heading(self):
        for accel in ((0., 0., 1.), (0., 0., -1.), (.8, .1, -.59)):
            with self.subTest(accel=accel):
                fusion = ComplementaryFusion(gravity_vector_correction=True)
                q = fusion.update(sample(0, accel))
                norm = math.sqrt(sum(v*v for v in accel))
                for actual, expected in zip(gravity_in_body(q), accel):
                    self.assertAlmostEqual(actual, expected/norm, places=12)
                self.assertAlmostEqual(euler_degrees(q)[2], 0., places=10)

    def test_pure_yaw_rotation_remains_visible_without_magnetometer(self):
        fusion = ComplementaryFusion(gravity_vector_correction=True)
        origin = fusion.update(sample(0, accel=(0., 0., -1.)))
        for index in range(1, 101):
            q = fusion.update(sample(index, accel=(0., 0., -1.), gyro=(0., 0., 90.)))
        self.assertAlmostEqual(rotation_angle(relative(q, origin)), 90., delta=.01)
        self.assertAlmostEqual(euler_degrees(q)[2], -90., delta=.01)

    def test_zero_correction_scale_matches_gyro_prediction_without_holding_clock(self):
        optional, legacy = ComplementaryFusion(True), ComplementaryFusion()
        for index in range(300):
            current = sample(index, accel=(.3*math.sin(index*.1), .2, .96),
                             gyro=(5., 10., 15.))
            q = optional.update(current, correction_scale=0.)
            self.assertEqual(q, legacy.update(current, correction_scale=0.))
        self.assertEqual(optional.last_device_us, 2990000)
        self.assertEqual(optional.last_time, 2.99)

    def test_magnetic_path_is_identical_with_optional_mode_enabled(self):
        optional, legacy = ComplementaryFusion(True), ComplementaryFusion()
        for index in range(600):
            current = sample(index, accel=(.2*math.sin(index*.07), .1, .98),
                             gyro=(2., -3., 8.), mag=(300., 40., -150.), flags=3)
            self.assertEqual(optional.update(current), legacy.update(current))

    def test_exact_antipodal_gravity_uses_finite_deterministic_horizontal_axis(self):
        fusion = ComplementaryFusion(True)
        fusion.q = (1., 0., 0., 0.)
        fusion.last_time, fusion.last_device_us = 0., 0
        q = fusion.update(sample(1, accel=(0., 0., -1.)))
        self.assertTrue(all(math.isfinite(value) for value in q))
        self.assertGreater(q[1], 0.)
        self.assertEqual(q[2:], (0., 0.))
        self.assertAlmostEqual(sum(value*value for value in q), 1., places=12)


if __name__ == "__main__":
    unittest.main()
