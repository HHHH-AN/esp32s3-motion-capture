"""Deterministic sensor-stream checks; no hardware, network, or sleeps required."""
from dataclasses import replace
import math
import unittest

from dashboard.attitude_stability import AttitudeStabilizer
from dashboard.models import SensorSample


def sample(t, gyro=(0., 0., 0.), accel=(0., 0., 1.), mag=(300., 0., 100.),
           *, device_t=None, flags=3):
    device_t = t if device_t is None else device_t
    return SensorSample(
        accel=accel, gyro=gyro, mag=mag, temperature=25., aux_temperature=25.,
        received_monotonic=100.+t, received_unix=1000.+t,
        node_id="imu_test", sequence=int(round(t*100)),
        device_us=int(round(device_t*1_000_000)) % 2**32,
        sensor_flags=flags,
    )


class AttitudeStabilityTests(unittest.TestCase):
    BIAS = (.7, -.4, .25)

    def assertBias(self, stabilizer, expected=None):
        expected = self.BIAS if expected is None else expected
        for actual, wanted in zip(stabilizer.bias, expected):
            self.assertAlmostEqual(actual, wanted, places=9)

    def calibrate(self, stabilizer, bias=None, start=0.):
        bias = self.BIAS if bias is None else bias
        stabilizer.start_calibration()
        accepted = []
        for i in range(481):
            if stabilizer.update(sample(start+i*.01, gyro=bias)):
                accepted.append(i)
        self.assertEqual(accepted, [480])
        self.assertTrue(stabilizer.calibrated)
        self.assertFalse(stabilizer.calibrating)
        self.assertAlmostEqual(stabilizer.progress, 1.)
        self.assertEqual(stabilizer.phase, "complete")
        return start+4.8

    def settle(self, stabilizer, start=4.8, bias=None):
        bias = self.BIAS if bias is None else bias
        for i in range(1, 82):
            stabilizer.update(sample(start+i*.01, gyro=bias))
        self.assertTrue(stabilizer.stationary)
        return start+.81

    def test_explicit_calibration_estimates_all_three_bias_axes(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        completed = []
        for i in range(481):
            # A zero-mean disturbance exercises averaging on each axis.
            noise = .02*math.sin(2*math.pi*i/20)
            gyro = tuple(b+noise*scale for b, scale in zip(self.BIAS, (1, -1, .5)))
            if stabilizer.update(sample(i*.01, gyro=gyro)):
                completed.append(i)
        self.assertEqual(completed, [480])
        for measured, expected in zip(stabilizer.bias, self.BIAS):
            self.assertAlmostEqual(measured, expected, places=7)
        original = sample(4.81, gyro=(1.7, -2.4, 3.25))
        corrected = stabilizer.corrected(original)
        for actual, expected in zip(corrected.gyro, (1., -2., 3.)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(original.gyro, (1.7, -2.4, 3.25))
        self.assertEqual(corrected.accel, original.accel)
        self.assertEqual(corrected.device_us, original.device_us)
        self.assertEqual(corrected.node_id, original.node_id)

    def test_stationary_data_never_calibrates_or_locks_without_request(self):
        stabilizer = AttitudeStabilizer()
        for i in range(1500):
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=self.BIAS)))
        self.assertFalse(stabilizer.calibrated)
        self.assertFalse(stabilizer.stationary)
        self.assertEqual(stabilizer.bias, (0., 0., 0.))

    def test_calibration_requires_both_wall_and_device_time(self):
        for arrival_step, device_step in ((.005, .01), (.01, .005)):
            with self.subTest(arrival_step=arrival_step, device_step=device_step):
                stabilizer = AttitudeStabilizer()
                stabilizer.start_calibration()
                for i in range(401):
                    self.assertFalse(stabilizer.update(sample(
                        i*arrival_step, gyro=self.BIAS, device_t=i*device_step)))
                self.assertFalse(stabilizer.calibrated)
                self.assertTrue(stabilizer.calibrating)
                self.assertGreaterEqual(stabilizer.progress, 0.)
                self.assertLess(stabilizer.progress, 1.)

    def test_four_seconds_with_too_few_samples_is_insufficient(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(49):
            self.assertFalse(stabilizer.update(sample(i*.1, gyro=self.BIAS)))
        self.assertFalse(stabilizer.calibrated)

    def test_no_device_timestamp_falls_back_to_arrival_time(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        result = False
        for i in range(481):
            result = stabilizer.update(replace(sample(i*.01, gyro=self.BIAS), device_us=None))
        self.assertTrue(result)
        self.assertTrue(stabilizer.calibrated)

    def test_disturbed_recalibration_preserves_previously_accepted_bias(self):
        stabilizer = AttitudeStabilizer()
        self.calibrate(stabilizer)
        old_bias = stabilizer.bias
        stabilizer.start_calibration()
        for i in range(481):
            gyro = (2.+(.5 if i % 2 else -.5), 0., 0.)
            self.assertFalse(stabilizer.update(sample(5.+i*.01, gyro=gyro)))
        self.assertTrue(stabilizer.calibrating)
        self.assertEqual(stabilizer.phase, "waiting")
        self.assertTrue(stabilizer.calibrated)
        self.assertEqual(stabilizer.bias, old_bias)

    def test_gyro_variation_or_magnetic_direction_trend_retries_without_replacing_old_bias(self):
        new_bias = (1.2, -.2, .4)
        for disturbance in ("gyro", "magnetic"):
            with self.subTest(disturbance=disturbance):
                stabilizer = AttitudeStabilizer()
                self.calibrate(stabilizer)
                old_bias = stabilizer.bias
                stabilizer.start_calibration(now=105.)
                for i in range(501):
                    gyro = new_bias
                    magnetic = (300., 0., 100.)
                    if disturbance == "gyro":
                        gyro = (new_bias[0]+(.5 if i % 2 else -.5), new_bias[1], new_bias[2])
                    else:
                        heading = i*.002
                        magnetic = (300.*math.cos(heading), 300.*math.sin(heading), 100.)
                    self.assertFalse(stabilizer.update(sample(5.+i*.01, gyro=gyro, mag=magnetic)))
                    self.assertEqual(stabilizer.bias, old_bias)
                self.assertTrue(stabilizer.calibrating)
                self.assertEqual(stabilizer.phase, "waiting")
                self.assertGreater(stabilizer.retries, 0)
                self.assertTrue(stabilizer.calibration_quality)
                completed = []
                for i in range(1, 502):
                    if stabilizer.update(sample(10.+i*.01, gyro=new_bias)):
                        completed.append(i)
                self.assertEqual(len(completed), 1)
                self.assertEqual(stabilizer.phase, "complete")
                self.assertBias(stabilizer, new_bias)

    def test_wait_phase_precedes_four_seconds_of_candidate_samples(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration(now=100.)
        self.assertEqual(stabilizer.phase, "waiting")
        for i in range(80):
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=self.BIAS)))
            self.assertEqual(stabilizer.phase, "waiting")
        stabilizer.update(sample(.8, gyro=self.BIAS))
        self.assertEqual(stabilizer.phase, "collecting")
        for i in range(81, 480):
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=self.BIAS)))
        self.assertFalse(stabilizer.calibrated)
        self.assertTrue(stabilizer.update(sample(4.8, gyro=self.BIAS)))
        self.assertEqual(stabilizer.phase, "complete")

    def test_expire_ends_request_after_thirty_seconds_without_any_sample(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration(now=100.)
        stabilizer.expire(129.99)
        self.assertTrue(stabilizer.calibrating)
        stabilizer.expire(130.)
        self.assertFalse(stabilizer.calibrating)
        self.assertFalse(stabilizer.calibrated)
        self.assertEqual(stabilizer.phase, "failed")

    def test_motion_retries_cannot_extend_absolute_timeout_or_replace_old_bias(self):
        stabilizer = AttitudeStabilizer()
        self.calibrate(stabilizer)
        old_bias = stabilizer.bias
        stabilizer.start_calibration(now=105.)
        for i in range(300):
            self.assertFalse(stabilizer.update(sample(5.+i*.1, gyro=(21., 0., 0.))))
            self.assertTrue(stabilizer.calibrating)
        stabilizer.expire(135.)
        self.assertFalse(stabilizer.calibrating)
        self.assertEqual(stabilizer.phase, "failed")
        self.assertTrue(stabilizer.calibrated)
        self.assertEqual(stabilizer.bias, old_bias)

    def test_large_motion_restarts_waiting_then_still_samples_finish_same_request(self):
        for gyro, accel in (((21., 0., 0.), (0., 0., 1.)),
                            ((0., 0., 0.), (0., 0., 1.3))):
            with self.subTest(gyro=gyro, accel=accel):
                stabilizer = AttitudeStabilizer()
                stabilizer.start_calibration()
                self.assertFalse(stabilizer.update(sample(0.)))
                self.assertFalse(stabilizer.update(sample(.01, gyro=gyro, accel=accel)))
                self.assertTrue(stabilizer.calibrating)
                self.assertEqual(stabilizer.phase, "waiting")
                self.assertFalse(stabilizer.calibrated)
                accepted = []
                for i in range(2, 503):
                    if stabilizer.update(sample(i*.01, gyro=self.BIAS)):
                        accepted.append(i)
                self.assertEqual(len(accepted), 1)
                self.assertGreaterEqual(accepted[0]*.01, 4.81)
                self.assertTrue(stabilizer.calibrated)
                self.assertEqual(stabilizer.phase, "complete")

    def test_accelerometer_direction_variation_rejects_calibration(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(481):
            accel = ((.03 if i % 2 else -.03), 0., math.sqrt(1.-.03**2))
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=self.BIAS, accel=accel)))
        self.assertFalse(stabilizer.calibrated)
        self.assertTrue(stabilizer.calibrating)
        self.assertEqual(stabilizer.phase, "waiting")

    def test_valid_magnetic_direction_change_rejects_steady_yaw_calibration(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(481):
            angle = math.radians(10*i/400)
            mag = (300.*math.cos(angle), 300.*math.sin(angle), 100.)
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=(0., 0., 2.5), mag=mag)))
        self.assertFalse(stabilizer.calibrated)
        self.assertTrue(stabilizer.calibrating)
        self.assertEqual(stabilizer.phase, "waiting")

    def test_invalid_magnetometer_is_not_used_as_motion_evidence(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        result = False
        for i in range(481):
            result = stabilizer.update(sample(
                i*.01, gyro=self.BIAS, mag=(300.*(-1 if i % 2 else 1), 0., 100.), flags=1))
        self.assertTrue(result)
        self.assertTrue(stabilizer.calibrated)

    def test_gap_cannot_be_used_to_complete_calibration(self):
        for arrival_t, device_t in ((4., 4.), (2.01, 4.)):
            with self.subTest(arrival_t=arrival_t, device_t=device_t):
                stabilizer = AttitudeStabilizer()
                stabilizer.start_calibration()
                for i in range(201):
                    stabilizer.update(sample(i*.01, gyro=self.BIAS))
                self.assertFalse(stabilizer.update(sample(
                    arrival_t, gyro=self.BIAS, device_t=device_t)))
                self.assertFalse(stabilizer.calibrating)
                self.assertFalse(stabilizer.calibrated)
                self.assertEqual(stabilizer.progress, 0.)

    def test_tcp_arrival_delay_keeps_calibration_when_device_samples_are_continuous(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        accepted = []
        for i in range(501):
            arrival = i*.01+(1. if i >= 200 else 0.)
            if stabilizer.update(sample(arrival, gyro=self.BIAS, device_t=i*.01)):
                accepted.append(i)
        self.assertEqual(len(accepted), 1)
        self.assertGreaterEqual(accepted[0], 480)
        self.assertTrue(stabilizer.calibrated)

    def test_arrival_gap_without_device_timestamp_cancels_calibration(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(201):
            stabilizer.update(replace(sample(i*.01, gyro=self.BIAS), device_us=None))
        stabilizer.update(replace(sample(3., gyro=self.BIAS), device_us=None))
        self.assertFalse(stabilizer.calibrating)
        self.assertFalse(stabilizer.calibrated)
        self.assertEqual(stabilizer.phase, "cancelled")

    def test_device_restart_cancels_calibration(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(201):
            stabilizer.update(sample(i*.01, gyro=self.BIAS))
        self.assertFalse(stabilizer.update(sample(2.01, gyro=self.BIAS, device_t=0.)))
        self.assertFalse(stabilizer.calibrating)
        self.assertFalse(stabilizer.calibrated)

    def test_micros_counter_wrap_is_a_continuous_stream(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        result = False
        for i in range(481):
            result = stabilizer.update(sample(i*.01, gyro=self.BIAS, device_t=4294.+i*.01))
        self.assertTrue(result)
        self.assertTrue(stabilizer.calibrated)

    def test_rest_requires_a_window_then_motion_releases_it_immediately(self):
        for speed in (1., 90.):
            with self.subTest(speed=speed):
                stabilizer = AttitudeStabilizer()
                end = self.calibrate(stabilizer)
                for i in range(1, 31):
                    stabilizer.update(sample(end+i*.01, gyro=self.BIAS))
                self.assertFalse(stabilizer.stationary)
                end = self.settle(stabilizer, end+.3)
                turning = sample(end+.01, gyro=(self.BIAS[0], self.BIAS[1], self.BIAS[2]+speed))
                stabilizer.update(turning)
                self.assertFalse(stabilizer.stationary)
                self.assertAlmostEqual(stabilizer.corrected(turning).gyro[2], speed)
                self.assertBias(stabilizer)

    def test_sustained_one_degree_per_second_motion_is_preserved(self):
        stabilizer = AttitudeStabilizer()
        end = self.calibrate(stabilizer)
        for i in range(1, 1001):
            turning = sample(end+i*.01, gyro=(self.BIAS[0], self.BIAS[1], self.BIAS[2]+1.))
            stabilizer.update(turning)
            self.assertFalse(stabilizer.stationary)
            self.assertAlmostEqual(stabilizer.corrected(turning).gyro[2], 1.)
        self.assertBias(stabilizer)

    def test_noisy_but_still_samples_can_calibrate_and_settle(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        result = False
        for i in range(481):
            gyro = (self.BIAS[0]+(.2 if i % 2 else -.2), self.BIAS[1], self.BIAS[2])
            result = stabilizer.update(sample(i*.01, gyro=gyro))
        self.assertTrue(result)
        for i in range(1, 101):
            gyro = (self.BIAS[0]+(.2 if i % 2 else -.2), self.BIAS[1], self.BIAS[2])
            stabilizer.update(sample(4.8+i*.01, gyro=gyro))
        self.assertTrue(stabilizer.stationary)

    def test_independent_three_axis_noise_is_not_compared_to_a_single_axis_limit(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        def noisy_gyro(i):
            signs = (1 if i % 2 else -1, 1 if i % 4 < 2 else -1,
                     1 if i % 8 < 4 else -1)
            return tuple(b+.24*s for b, s in zip(self.BIAS, signs))
        for i in range(481):
            stabilizer.update(sample(i*.01, gyro=noisy_gyro(i)))
        self.assertTrue(stabilizer.calibrated)
        self.assertGreater(stabilizer.calibration_quality['gyro_std_dps'], .35)
        self.assertLess(max(stabilizer.calibration_quality['gyro_axis_std_dps']), .25)
        for actual, expected in zip(stabilizer.bias, self.BIAS):
            self.assertAlmostEqual(actual, expected, delta=.002)
        for i in range(1, 101):
            stabilizer.update(sample(4.8+i*.01, gyro=noisy_gyro(480+i)))
        self.assertTrue(stabilizer.stationary)

    def test_measured_noise_level_can_be_averaged_without_learning_a_trend(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(481):
            gyro = (self.BIAS[0]+(.40 if i % 2 else -.40), *self.BIAS[1:])
            stabilizer.update(sample(i*.01, gyro=gyro))
        self.assertTrue(stabilizer.calibrated)
        self.assertGreater(stabilizer.calibration_quality['gyro_max_axis_std_dps'], .35)
        self.assertLess(stabilizer.calibration_quality['gyro_max_axis_std_dps'], .45)
        self.assertAlmostEqual(stabilizer.bias[0], self.BIAS[0], delta=.002)

    def test_uncorrelated_magnetic_noise_does_not_block_gyro_bias_but_heading_is_gated(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(481):
            stabilizer.update(sample(i*.01, gyro=self.BIAS,
                                     mag=(300., 50.*math.sin(i), 100.)))
        self.assertTrue(stabilizer.calibrated)
        self.assertBias(stabilizer)
        self.assertTrue(stabilizer.calibration_quality['magnetic_noisy'])
        guarded = stabilizer.guard_magnetometer(sample(4.81, mag=(300., 0., 100.)))
        self.assertEqual(guarded.sensor_flags, 1)

    def test_slowly_changing_gyro_mean_is_rejected_even_with_small_axis_std(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(481):
            gyro = (self.BIAS[0]+i*.001, *self.BIAS[1:])
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=gyro)))
        self.assertFalse(stabilizer.calibrated)
        self.assertGreater(stabilizer.calibration_quality['gyro_mean_change_dps'], .25)
        self.assertEqual(stabilizer.phase, 'waiting')

    def test_large_constant_offset_still_requires_stationary_startup_reset(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        for i in range(481):
            self.assertFalse(stabilizer.update(sample(i*.01, gyro=(18., -4., -1.5))))
        self.assertFalse(stabilizer.calibrated)
        self.assertEqual(stabilizer.phase, 'waiting')
        self.assertEqual(stabilizer.bias, (0., 0., 0.))

    def test_sustained_point_two_degree_per_second_does_not_settle(self):
        stabilizer = AttitudeStabilizer()
        end = self.calibrate(stabilizer)
        for i in range(1, 151):
            gyro = (self.BIAS[0], self.BIAS[1], self.BIAS[2]+.2)
            turning = sample(end+i*.01, gyro=gyro)
            stabilizer.update(turning)
            self.assertFalse(stabilizer.stationary)
            self.assertAlmostEqual(stabilizer.corrected(turning).gyro[2], .2)

    def test_magnetic_guard_rejects_strong_field_without_changing_original(self):
        stabilizer = AttitudeStabilizer()
        self.calibrate(stabilizer)
        original = sample(4.01, gyro=(1., 2., 3.), mag=(2500., 0., 0.))
        guarded = stabilizer.guard_magnetometer(original)
        self.assertFalse(guarded.sensor_flags & 2)
        self.assertEqual(guarded.sensor_flags & 1, 1)
        self.assertEqual(guarded.gyro, original.gyro)
        self.assertEqual(guarded.mag, original.mag)
        self.assertEqual(original.sensor_flags, 3)
        normal = sample(4.02)
        self.assertEqual(stabilizer.guard_magnetometer(normal).sensor_flags, 3)

    def test_magnetic_guard_rejects_noisy_weak_horizontal_field_after_valid_calibration(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        accepted = False
        for i in range(481):
            magnetic = (30.+10.*math.sin(i), 0., 500.)
            accepted = stabilizer.update(sample(i*.01, gyro=self.BIAS, mag=magnetic))
        self.assertTrue(accepted)
        self.assertTrue(stabilizer.calibrated)
        quality = stabilizer.calibration_quality
        self.assertLess(quality["mag_relative_std"], .05)
        self.assertLess(quality["mag_direction_change_deg"], 3.)
        original = sample(4.81, gyro=self.BIAS, mag=(30., 0., 500.))
        guarded = stabilizer.guard_magnetometer(original)
        self.assertEqual(guarded.sensor_flags, 1)
        self.assertFalse(stabilizer.magnetic_used)
        self.assertEqual(original.sensor_flags, 3)
        self.assertEqual(guarded.gyro, original.gyro)

    def test_magnetic_guard_retains_strong_horizontal_field_with_low_noise(self):
        stabilizer = AttitudeStabilizer()
        stabilizer.start_calibration()
        accepted = False
        for i in range(481):
            magnetic = (300.+math.sin(i), 0., 500.)
            accepted = stabilizer.update(sample(i*.01, gyro=self.BIAS, mag=magnetic))
        self.assertTrue(accepted)
        self.assertTrue(stabilizer.calibrated)
        original = sample(4.81, gyro=self.BIAS, mag=(300., 0., 500.))
        guarded = stabilizer.guard_magnetometer(original)
        self.assertEqual(guarded.sensor_flags, 3)
        self.assertTrue(stabilizer.magnetic_used)
        self.assertEqual(guarded, original)

    def test_acceleration_disturbance_releases_rest(self):
        stabilizer = AttitudeStabilizer()
        end = self.calibrate(stabilizer)
        end = self.settle(stabilizer, end)
        stabilizer.update(sample(end+.01, gyro=self.BIAS, accel=(0., 0., 1.1)))
        self.assertFalse(stabilizer.stationary)

    def test_reset_window_preserves_bias_but_clear_removes_it(self):
        stabilizer = AttitudeStabilizer()
        end = self.calibrate(stabilizer)
        self.settle(stabilizer, end)
        stabilizer.start_calibration()
        stabilizer.update(sample(6., gyro=self.BIAS))
        stabilizer.reset_window("连接中断")
        self.assertFalse(stabilizer.calibrating)
        self.assertFalse(stabilizer.stationary)
        self.assertTrue(stabilizer.calibrated)
        self.assertBias(stabilizer)
        self.assertIn("连接中断", stabilizer.message)
        stabilizer.clear()
        self.assertFalse(stabilizer.calibrated)
        self.assertFalse(stabilizer.calibrating)
        self.assertFalse(stabilizer.stationary)
        self.assertEqual(stabilizer.bias, (0., 0., 0.))
        self.assertEqual(stabilizer.progress, 0.)


if __name__ == "__main__":
    unittest.main()
