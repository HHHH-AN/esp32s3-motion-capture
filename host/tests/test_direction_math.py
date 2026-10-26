"""Known geometries for functional direction calibration; no hardware input."""
from copy import deepcopy
import math
import random
import unittest

from dashboard.body_math import IDENTITY, angle_degrees, inverse, multiply, rotate
from dashboard.direction_calibration import CalibrationError, fit_direction, summarize_neutral
from dashboard.fusion import euler_quaternion


def axis_quaternion(axis, degrees):
    half = math.radians(degrees)/2
    length = math.hypot(*axis)
    return (math.cos(half),*(math.sin(half)*v/length for v in axis))


def calibration_windows(mount=IDENTITY, fusion=IDENTITY, peak=55., axis=(0.,-1.,0.), noise=0.):
    rng = random.Random(193)
    def sample(t, angle=0., speed=0.):
        body = axis_quaternion(axis,angle)
        sensor_world = multiply(body,mount)
        q = multiply(fusion,sensor_world)
        accel = rotate((0.,0.,1.),inverse(sensor_world))
        gyro = rotate(tuple(v*speed/math.hypot(*axis) for v in axis),inverse(mount))
        if noise:
            q = multiply(q,euler_quaternion(*(rng.gauss(0,math.radians(noise)) for _ in range(3))))
            accel = tuple(v+rng.gauss(0,noise*.002) for v in accel)
            gyro = tuple(v+rng.gauss(0,noise*.1) for v in gyro)
        return {"time":t,"quaternion":q,"accel":accel,"gyro":gyro,
                "device_id":"deviceA","body_slot":"right_upper_arm","boot_id":"boot-1",
                "processing_profile":"six_axis_relative","fusion_version":"test-provider/1"}
    neutral = [sample(i*.01) for i in range(101)]
    motion = []
    for i in range(361):
        t = i*.01
        if t < .35:
            angle = speed = 0.
        elif t < 1.55:
            f = (t-.35)/1.2
            angle = peak*(1-math.cos(math.pi*f))/2
            speed = peak*math.pi*math.sin(math.pi*f)/2/1.2
        elif t < 1.95:
            angle, speed = peak,0.
        elif t < 3.15:
            f = (t-1.95)/1.2
            angle = peak*(1+math.cos(math.pi*f))/2
            speed = -peak*math.pi*math.sin(math.pi*f)/2/1.2
        else:
            angle = speed = 0.
        motion.append(sample(1.1+t,angle,speed))
    return neutral,motion


class FunctionalDirectionMathTests(unittest.TestCase):
    def test_arbitrary_mount_and_independent_fusion_frame_recovered(self):
        mounts = [IDENTITY,euler_quaternion(math.pi/2,0,0),euler_quaternion(0,math.pi,0),
                  euler_quaternion(.73,-1.1,2.3),euler_quaternion(-2.7,.2,-.9)]
        fusions = [euler_quaternion(0,0,math.radians(146.6)),
                   euler_quaternion(0,0,math.radians(-107.3)),euler_quaternion(.3,.5,-2.1)]
        for mount in mounts:
            for fusion in fusions:
                with self.subTest(mount=mount,fusion=fusion):
                    neutral,motion = calibration_windows(mount,fusion)
                    fitted = fit_direction(neutral,motion)
                    self.assertLess(angle_degrees(fitted["sensor_to_body"],mount),1e-7)
                    self.assertLess(angle_degrees(fitted["fusion_to_world"],inverse(fusion)),1e-7)
                    for actual in (euler_quaternion(.8,-.3,.2),axis_quaternion((0,-1,0),40),
                                   axis_quaternion((-1,0,0),35),axis_quaternion((0,-1,0),80)):
                        q = multiply(multiply(fusion,actual),mount)
                        result = multiply(multiply(fitted["fusion_to_world"],q),fitted["mount_bone_to_sensor"])
                        self.assertLess(angle_degrees(result,actual),1e-7)

    def test_neutral_only_can_zero_but_heading_conjugation_remains_wrong(self):
        mount = euler_quaternion(.5,-.7,.9)
        fusion = euler_quaternion(0,0,2.1)
        neutral,motion = calibration_windows(mount,fusion)
        q0 = summarize_neutral(neutral)["reference"]
        action = axis_quaternion((-1,0,0),40)
        q = multiply(multiply(fusion,action),mount)
        uncalibrated = multiply(q,inverse(q0))
        self.assertLess(angle_degrees(multiply(q0,inverse(q0)),IDENTITY),1e-7)
        self.assertGreater(angle_degrees(uncalibrated,action),30)
        fitted = fit_direction(neutral,motion)
        corrected = multiply(multiply(fitted["fusion_to_world"],q),fitted["mount_bone_to_sensor"])
        self.assertLess(angle_degrees(corrected,action),1e-7)

    def test_unknown_amplitude_and_moderate_noise_are_not_exact_angle_targets(self):
        for peak in (24.,47.,88.,123.):
            neutral,motion = calibration_windows(euler_quaternion(.6,.4,1.7),euler_quaternion(0,0,-2.2),peak=peak,noise=.08)
            fitted = fit_direction(neutral,motion)
            self.assertLess(angle_degrees(fitted["sensor_to_body"],euler_quaternion(.6,.4,1.7)),.3)
            self.assertFalse(fitted["quality"]["amplitude_ground_truth_required"])

    def test_one_endpoint_pose_or_tiny_motion_cannot_fit(self):
        neutral,motion = calibration_windows(peak=3)
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(neutral,motion)
        self.assertEqual(caught.exception.code,"insufficient_excursion")
        with self.assertRaises(CalibrationError):
            fit_direction(neutral,[motion[150]])

    def test_vertical_hinge_and_non_hinge_constraints_are_rejected(self):
        neutral,motion = calibration_windows(axis=(0,0,1))
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(neutral,motion)
        self.assertEqual(caught.exception.code,"axis_gravity_contradiction")
        neutral,motion = calibration_windows()
        for i,s in enumerate(motion):
            s["quaternion"] = multiply(s["quaternion"],axis_quaternion((1,0,0),25*math.sin(i/len(motion)*2*math.pi)))
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(neutral,motion)
        self.assertEqual(caught.exception.code,"non_hinge_motion")

    def test_incomplete_return_drift_and_missing_tail_are_rejected(self):
        neutral,motion = calibration_windows()
        incomplete = motion[:180]
        with self.assertRaises(CalibrationError):
            fit_direction(neutral,incomplete)
        drifted = deepcopy(motion)
        for i,s in enumerate(drifted):
            s["quaternion"] = multiply(axis_quaternion((0,0,1),18*i/(len(drifted)-1)),s["quaternion"])
        with self.assertRaises(CalibrationError):
            fit_direction(neutral,drifted)
        restless = deepcopy(motion)
        for s in restless[-30:]:
            s["gyro"] = (4.,0.,0.)
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(neutral,restless)
        self.assertEqual(caught.exception.code,"return_not_stationary")

    def test_identity_session_mode_reference_axes_and_gap_invalidates_fit(self):
        neutral,motion = calibration_windows()
        for field,value in (("device_id","other"),("body_slot","right_forearm"),("boot_id","boot2"),
                            ("processing_profile","magnetic_guarded"),("fusion_version","new/2")):
            changed = deepcopy(motion)
            changed[100][field] = value
            with self.subTest(field=field),self.assertRaises(CalibrationError) as caught:
                fit_direction(neutral,changed)
            self.assertEqual(caught.exception.code,"identity_changed")
        changed = motion[:100]+motion[120:]
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(neutral,changed)
        self.assertEqual(caught.exception.code,"sample_gap")

    def test_neutral_residual_gyro_noise_and_nonfinite_are_rejected(self):
        neutral,motion = calibration_windows()
        moving = deepcopy(neutral)
        moving[50]["gyro"] = (19.,0.,0.)
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(moving,motion)
        self.assertEqual(caught.exception.code,"neutral_not_stationary")
        neutral[0]["quaternion"] = (float("nan"),0.,0.,0.)
        with self.assertRaises(CalibrationError):
            fit_direction(neutral,motion)

    def test_fitted_transforms_and_windows_are_independent_snapshots(self):
        neutral,motion = calibration_windows()
        fit = fit_direction(neutral,motion)
        before = deepcopy(fit["windows"])
        motion[100]["quaternion"] = (0.,1.,0.,0.)
        self.assertEqual(fit["windows"],before)
        self.assertEqual(fit["windows"]["forward_raise_return"]["samples"],len(motion))
        self.assertFalse(fit["quality"]["direction_label_verified_by_sensor"])
        self.assertIn("未参与拟合的向外侧举",fit["validation_required"])

    def test_fusion_heading_motion_without_sensor_rotation_is_rejected(self):
        neutral,motion=calibration_windows()
        for sample in motion:
            sample["gyro"]=(0.,0.,0.)
        with self.assertRaises(CalibrationError) as caught:
            fit_direction(neutral,motion)
        self.assertEqual(caught.exception.code,"gyro_orientation_contradiction")


if __name__ == "__main__":
    unittest.main()
