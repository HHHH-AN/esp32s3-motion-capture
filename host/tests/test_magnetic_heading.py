"""Known magnetic truth, residual gyro drift and disturbed-field fallback."""
from dataclasses import replace
import math
import unittest

from dashboard.attitude_config import load_attitude_config
from dashboard.body_engine import BodyEngine
from dashboard.body_math import IDENTITY, angle_degrees
from dashboard.models import SensorSample


DEVICE = "imu_305A6077C398"


def sample(index, gyro=(0., 0., .5), mag=(300., 0., 100.)):
    return SensorSample((0., 0., 1.), gyro, mag, 25., 0.,
                        received_monotonic=100.+index*.01,
                        received_unix=1000.+index*.01,
                        device_us=index*10000, sequence=index, node_id=DEVICE,
                        body_slot="right_forearm", boot_id="same-boot", protocol_version="IMU3")


class MagneticHeadingTests(unittest.TestCase):
    def test_sixty_second_bias_is_bounded_by_magnetic_heading_without_hold(self):
        guarded = BodyEngine()
        config = load_attitude_config()
        config["device_profiles"][DEVICE] = "six_axis_relative"
        six_axis = BodyEngine(attitude_config=config)
        for i in range(6001):
            raw = sample(i)
            guarded.ingest(raw, "tcp")
            six_axis.ingest(raw, "tcp")
        a, b = guarded.devices[DEVICE], six_axis.devices[DEVICE]
        self.assertTrue(a.stability.magnetic_used)
        self.assertFalse(a.stability.stationary)
        self.assertLess(angle_degrees(a.quaternion, IDENTITY), 2.)
        self.assertGreater(angle_degrees(b.quaternion, IDENTITY), 29.)

    def test_real_rotation_is_not_held_and_heading_wrap_does_not_jump(self):
        engine = BodyEngine()
        previous = None
        for i in range(401):
            yaw = math.radians(i*.9)
            engine.ingest(sample(i, gyro=(0.,0.,90.),
                                 mag=(300.*math.cos(yaw),-300.*math.sin(yaw),100.)), "tcp")
            node = engine.devices[DEVICE]
            if previous:
                self.assertLess(angle_degrees(previous,node.quaternion), 1.1)
            truth = (math.cos(yaw/2),0.,0.,math.sin(yaw/2))
            self.assertLess(angle_degrees(node.quaternion,truth), .05)
            previous = node.quaternion

    def test_disturbed_field_is_rejected_without_erasing_raw_data(self):
        engine = BodyEngine()
        for i in range(100):
            engine.ingest(sample(i,gyro=(0.,0.,0.)),"tcp")
        node = engine.devices[DEVICE]
        before = node.quaternion
        engine.ingest(sample(100,gyro=(0.,0.,0.),mag=(0.,5000.,0.)),"tcp")
        self.assertFalse(node.stability.magnetic_used)
        self.assertEqual(node.last_sample.mag,(0.,5000.,0.))
        self.assertLess(angle_degrees(before,node.quaternion),1e-8)
        engine.ingest(sample(101,gyro=(0.,0.,0.),mag=(0.,0.,100.)),"tcp")
        self.assertFalse(node.stability.magnetic_used)


if __name__ == "__main__":
    unittest.main()
