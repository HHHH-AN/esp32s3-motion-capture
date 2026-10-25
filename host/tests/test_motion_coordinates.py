import asyncio
import csv
import itertools
import math
from pathlib import Path
from time import monotonic
import tempfile
import unittest

from dashboard.coordinates import CoordinateSettings
from dashboard.fusion import euler_quaternion
from dashboard.kinematics import rotate
from dashboard.models import SensorSample
from dashboard.motion import DisplacementEstimator
from dashboard.recordings import replay_data
from dashboard.service import Runtime


def sample(index, accel=(0,0,1), gyro=(0,0,0)):
    return SensorSample(accel,gyro,(30,0,10),25,0,received_monotonic=index*.01,device_us=index*10000)


def initialized_motion():
    motion=DisplacementEstimator()
    motion.start(2)
    for i in range(102):
        motion.update(sample(i),(1,0,0,0))
    assert motion.phase=="measuring"
    return motion


class MotionTests(unittest.TestCase):
    def test_stationary_displacement_is_zero(self):
        motion=initialized_motion()
        for i in range(102,202):
            motion.update(sample(i),(1,0,0,0))
        self.assertEqual(motion.position,(0,0,0))

    def test_known_acceleration_matches_analytic_displacement(self):
        motion=initialized_motion()
        for i in range(102,202):
            motion.update(sample(i,accel=(1/9.80665,0,1)),(1,0,0,0))
        self.assertAlmostEqual(motion.position[0],.5,delta=.02)
        self.assertAlmostEqual(motion.velocity[0],1,delta=.02)
        self.assertAlmostEqual(motion.position[2],0)
        last_velocity=motion.velocity
        motion.stop()
        self.assertEqual(motion.velocity,last_velocity)

    def test_tilted_stationary_gravity_is_removed(self):
        motion=DisplacementEstimator()
        motion.start(2)
        q=euler_quaternion(.5,-.6,.3)
        acceleration=rotate((0,0,1),(q[0],-q[1],-q[2],-q[3]))
        for i in range(210):
            motion.update(sample(i,accel=acceleration),q)
        for value in motion.position:
            self.assertAlmostEqual(value,0,places=6)

    def test_initialization_rejects_movement(self):
        motion=DisplacementEstimator()
        motion.start()
        for i in range(200):
            motion.update(sample(i,gyro=(20,0,0)),(1,0,0,0))
        self.assertEqual(motion.phase,"initializing")
        self.assertEqual(motion.position,(0,0,0))

    def test_time_limit_and_gap_stop_estimation(self):
        motion=initialized_motion()
        for i in range(102,305):
            motion.update(sample(i),(1,0,0,0))
        self.assertEqual(motion.phase,"stopped")
        self.assertAlmostEqual(motion.elapsed,2)
        motion=initialized_motion()
        motion.update(sample(150),(1,0,0,0))
        self.assertEqual(motion.phase,"stopped")
        self.assertIn("间隔",motion.message)

    def test_display_sign_does_not_change_integrator(self):
        motion=initialized_motion()
        motion.position=(1,2,3)
        settings=CoordinateSettings(displacement_signs=(-1,1,-1))
        self.assertEqual(motion.payload(settings)["position"],(-1,2,-3))
        self.assertEqual(motion.position,(1,2,3))

    def test_disabling_zupt_does_not_force_stationary_velocity_to_zero(self):
        motion=initialized_motion()
        motion.velocity=(1,0,0)
        for i in range(102,152):
            motion.update(sample(i),(1,0,0,0))
        self.assertTrue(motion.stationary)
        self.assertEqual(motion.velocity,(1,0,0))
        self.assertAlmostEqual(motion.position[0],.5)
        self.assertEqual(motion.payload(CoordinateSettings())["quality"],"inertial_only")

    def test_continuous_tracking_does_not_end_after_30_seconds(self):
        motion=DisplacementEstimator()
        motion.start(0,True,"balanced")
        for i in range(4000):
            motion.update(sample(i),(1,0,0,0))
        self.assertEqual(motion.phase,"measuring")
        self.assertGreater(motion.elapsed,30)
        self.assertEqual(motion.position,(0,0,0))
        self.assertEqual(motion.payload(CoordinateSettings())["quality"],"stationary_constraint")

    def test_continuous_tracking_reinitializes_after_gap_without_fabricating_motion(self):
        motion=DisplacementEstimator()
        motion.start(0,True,"balanced")
        for i in range(110):
            motion.update(sample(i),(1,0,0,0))
        motion.position=(1,2,3)
        motion.velocity=(2,0,0)
        motion.update(sample(160),(1,0,0,0))
        self.assertEqual(motion.phase,"initializing")
        self.assertEqual(motion.position,(1,2,3))
        self.assertEqual(motion.velocity,(0,0,0))
        for i in range(161,275):
            motion.update(sample(i),(1,0,0,0))
        self.assertEqual(motion.phase,"measuring")
        self.assertEqual(motion.position,(1,2,3))
        self.assertEqual(motion.payload(CoordinateSettings())["sampling_gaps"],1)

    def test_stationary_constraint_prevents_bias_drift(self):
        motion=DisplacementEstimator()
        motion.start(0,True,"balanced")
        for i in range(110):
            motion.update(sample(i),(1,0,0,0))
        motion.velocity=(.2,.1,0)
        for i in range(110,400):
            motion.update(sample(i,accel=(.015,0,1)),(1,0,0,0))
        held=motion.position
        for i in range(400,1400):
            motion.update(sample(i,accel=(.015,0,1)),(1,0,0,0))
        self.assertEqual(motion.position,held)
        self.assertEqual(motion.velocity,(0,0,0))
        # A static single pose must not learn a lateral attitude residual as bias.
        self.assertAlmostEqual(motion.accel_reference_g,1.0)
        motion.stop()
        self.assertEqual(motion.payload(CoordinateSettings())["quality"],"inactive")

    def test_position_is_expressed_in_the_same_reference_as_orientation(self):
        motion=initialized_motion()
        motion.position=(1,0,0)
        reference=euler_quaternion(0,0,math.pi/2)
        position=motion.payload(CoordinateSettings(),reference)["position"]
        self.assertAlmostEqual(position[0],0,places=7)
        self.assertAlmostEqual(position[1],-1,places=7)

    def test_single_node_api_uses_estimated_pose_instead_of_skeleton_rest_position(self):
        runtime=Runtime(coordinate_file=None)
        runtime.motion.position=(1,0,0)
        runtime._origin=euler_quaternion(0,0,math.pi/2)
        runtime.coordinates=CoordinateSettings(displacement_signs=(1,-1,1))
        payload=runtime.payload()
        position=payload["pose"]["position"]
        self.assertAlmostEqual(position[0],0,places=7)
        self.assertAlmostEqual(position[1],1,places=7)
        self.assertEqual(payload["nodes"][0]["position"],position)
        self.assertEqual(payload["trajectory"]["body"],position)

    def test_rotation_without_translation_does_not_create_position(self):
        motion=DisplacementEstimator()
        motion.start(0,True,"balanced")
        for i in range(110):
            motion.update(sample(i),(1,0,0,0))
        for i in range(110,310):
            q=euler_quaternion((i-110)*.003,0,0)
            acceleration=rotate((0,0,1),(q[0],-q[1],-q[2],-q[3]))
            motion.update(sample(i,accel=acceleration,gyro=(17.2,0,0)),q)
        for value in motion.position:
            self.assertAlmostEqual(value,0,places=6)


class CoordinateTests(unittest.TestCase):
    def test_all_24_right_handed_axis_rotations_are_accepted(self):
        accepted=0
        for axes in itertools.permutations("XYZ"):
            for signs in itertools.product(("+","-"),repeat=3):
                try:
                    settings=CoordinateSettings.parse({"sensor_axes":[s+a for s,a in zip(signs,axes)]})
                except ValueError:
                    continue
                accepted+=1
                self.assertAlmostEqual(sum(v*v for v in settings.sensor_vector((1,2,3))),14)
        self.assertEqual(accepted,24)

    def test_left_handed_and_duplicate_axes_are_rejected(self):
        for axes in [["-X","+Y","+Z"],["+X","+X","+Z"],["+Y","+X","+Z"]]:
            with self.assertRaises(ValueError):
                CoordinateSettings.parse({"sensor_axes":axes})

    def test_mapping_is_applied_to_all_sensors_and_persisted(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/"coordinates.json"
                runtime=Runtime(coordinate_file=path,recording_dir=Path(folder)/"recordings")
                await runtime.command({"action":"set_coordinates","coordinates":{"sensor_axes":["-X","-Y","+Z"],"displacement_signs":[-1,1,1]}})
                self.assertEqual(Runtime(coordinate_file=path).coordinates.sensor_axes,("-X","-Y","+Z"))
                runtime.start_recording()
                await runtime.consume(SensorSample((1,2,3),(4,5,6),(7,8,9),25,0))
                node=runtime.payload()["nodes"][0]
                self.assertEqual(node["accel"],(-1,-2,3))
                self.assertEqual(node["gyro"],(-4,-5,6))
                self.assertEqual(node["mag"],(-7,-8,9))
                directory=Path(runtime.record_path)
                runtime.stop_recording()
                with (directory/"imu-data.csv").open(encoding="utf-8-sig") as handle:
                    row=next(csv.DictReader(handle))
                self.assertEqual(row["加速度X"],"-1")
                self.assertEqual(row["原始加速度X"],"1")
                self.assertIn("motion",replay_data(directory.name,runtime.recording_dir)["frames"][0])
        asyncio.run(scenario())

    def test_zeroed_display_attitude_does_not_inject_gravity(self):
        async def scenario():
            runtime=Runtime(coordinate_file=None)
            # Feed synthetic monotonic samples to avoid the live age guard in commands.
            runtime.motion.start(2)
            base=monotonic()
            for i in range(220):
                observation=sample(i,accel=(0,.5,math.sqrt(.75)))
                observation.received_monotonic=base+i*.01
                await runtime.consume(observation)
                if i==101:
                    runtime._origin=runtime.fusion.q
            self.assertEqual(runtime.motion.phase,"measuring")
            self.assertGreater(runtime.motion.elapsed,1)
            for value in runtime.motion.position:
                self.assertAlmostEqual(value,0,places=5)
        asyncio.run(scenario())

    def test_mapping_rejected_while_recording(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as folder:
                runtime=Runtime(coordinate_file=None,recording_dir=Path(folder))
                runtime.start_recording()
                await runtime.command({"action":"set_coordinates","coordinates":{"sensor_axes":["-X","-Y","+Z"]}})
                self.assertEqual(runtime.coordinates.sensor_axes,("+X","+Y","+Z"))
                self.assertIn("停止记录",runtime.message)
                runtime.stop_recording()
        asyncio.run(scenario())
