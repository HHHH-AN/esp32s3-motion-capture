"""Teammate filter/calibrator through our body pipeline, without physical I/O."""
import asyncio
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
from time import monotonic
import unittest

from dashboard.attitude_config import load_attitude_config, validate_attitude_config
from dashboard.body_engine import BodyEngine
from dashboard.body_math import IDENTITY, angle_degrees
from dashboard.body_recording import BodyReplay
from dashboard.body_runtime import BodyRuntime
from dashboard.fusion import ComplementaryFusion, euler_degrees
from dashboard.models import SensorSample
from test_gravity_vector_fusion import noisy_pitch_return


def sample(index, device="test", slot="head", bias=(0.,0.,0.), boot="boot1"):
    return SensorSample((0.,0.,1.),bias,(300.,0.,100.),25.,0.,
                        received_monotonic=100+index*.01,node_id=device,
                        sequence=index,device_us=index*10000,body_slot=slot,
                        boot_id=boot,protocol_version="IMU3")


class PartnerDriftPipelineTests(unittest.TestCase):
    def test_identity_profiles_do_not_infer_body_slot_or_replace_sensor_axes(self):
        engine = BodyEngine()
        engine.ingest(replace(sample(0,device="imu_305A6077C398"),body_slot=None),"arbitrary-usb")
        engine.ingest(sample(0,device="imu_149B6077C398"),"arbitrary-tcp")
        a,b = engine.devices["imu_305A6077C398"],engine.devices["imu_149B6077C398"]
        self.assertEqual(a.processing_profile,"magnetic_guarded")
        self.assertEqual(b.processing_profile,"magnetic_guarded")
        self.assertIsNone(a.body_slot)
        self.assertEqual(a.coordinates.sensor_axes,("+X","+Y","+Z"))
        self.assertTrue(a.stability.magnetic_used)
        self.assertTrue(b.stability.magnetic_used)

    def test_magnetic_perturbation_cannot_rotate_six_axis_device(self):
        a,b = "imu_305A6077C398","other"
        config = load_attitude_config()
        config["device_profiles"][a] = "six_axis_relative"
        engine = BodyEngine(attitude_config=config)
        for i in range(600):
            mag = (0.,300.,100.) if i>100 else (300.,0.,100.)
            for device in (a,b):
                engine.ingest(replace(sample(i,device=device,slot=None),mag=mag),device)
        self.assertLess(angle_degrees(engine.devices[a].quaternion,IDENTITY),1e-8)
        self.assertGreater(angle_degrees(engine.devices[b].quaternion,IDENTITY),30)
        self.assertEqual(engine.devices[a].last_sample.mag,(0.,300.,100.))

    def test_vertical_pitch_regression_is_fixed_in_actual_node_processor(self):
        engine = BodyEngine()
        old = ComplementaryFusion()
        for i, raw in noisy_pitch_return(88.5):
            old.update(raw)
            engine.ingest(replace(raw,node_id="vertical",body_slot="left_forearm",boot_id="synth",sequence=i,protocol_version="IMU3"),"offline")
        node = engine.devices["vertical"]
        self.assertFalse(node.stability.calibrated)
        self.assertFalse(node.stability.stationary)
        self.assertLess(abs(euler_degrees(node.quaternion)[2]),1.5)
        self.assertGreater(abs(euler_degrees(old.q)[2]),15)
        self.assertEqual(node.valid_frames,2401)

    def test_successful_bias_requires_new_installation_and_is_applied_to_initialization(self):
        engine = BodyEngine()
        bias = (3.,-.7,6.)
        engine.ingest(sample(0,bias=bias),"offline")
        engine.devices["test"].reference = IDENTITY
        engine.calibrate_bias("test",now=100.)
        self.assertFalse(engine.devices["test"].initialized)
        for i in range(1,482):
            engine.ingest(sample(i,bias=bias),"offline")
        node = engine.devices["test"]
        self.assertTrue(node.stability.calibrated)
        self.assertFalse(node.initialized)
        for actual,expected in zip(node.stability.bias,bias):
            self.assertAlmostEqual(actual,expected,9)
        engine.begin_initialization(now=104.81)
        engine.finish_initialization(now=104.81)
        for i in range(482,584):
            engine.ingest(sample(i,bias=bias),"offline")
        state=engine.snapshot(now=105.83)
        self.assertEqual(state["initialization"]["status"],"complete")
        self.assertTrue(node.initialized)

    def test_timeout_and_cancellation_preserve_old_bias_without_reusing_reference(self):
        engine = BodyEngine()
        engine.ingest(sample(0),"offline")
        node=engine.devices["test"]
        node.stability.bias=(.2,-.1,.3)
        node.stability.calibrated=True
        node.reference=IDENTITY
        engine.calibrate_bias("test",now=100.)
        engine.snapshot(now=130.)
        self.assertEqual(node.stability.phase,"failed")
        self.assertEqual(node.stability.bias,(.2,-.1,.3))
        self.assertFalse(node.initialized)
        self.assertTrue(any(e["type"]=="bias_calibration_timeout" for e in engine.pop_events()))
        engine.ingest(sample(3001),"offline")
        engine.calibrate_bias("test",now=130.01)
        engine.cancel_calibration("test")
        self.assertEqual(node.stability.phase,"cancelled")
        self.assertEqual(node.stability.bias,(.2,-.1,.3))

    def test_clock_rollback_with_continuing_sequence_discards_calibration(self):
        engine=BodyEngine()
        engine.ingest(sample(100),"offline")
        node=engine.devices["test"]
        node.stability.bias=(.2,.3,.4)
        node.stability.calibrated=True
        node.reference=IDENTITY
        engine.ingest(replace(sample(101),device_us=1),"offline")
        self.assertFalse(node.initialized)
        self.assertFalse(node.stability.calibrated)
        self.assertEqual(node.stability.bias,(0.,0.,0.))
        self.assertEqual(node.valid_frames,2)
        self.assertTrue(any(e["type"]=="clock_reference_reset" for e in engine.pop_events()))

    def test_profile_switch_is_local_versioned_and_invalidates_reference(self):
        engine=BodyEngine()
        engine.ingest(sample(0,device="a"),"a")
        engine.ingest(sample(0,device="b",slot="pelvis"),"b")
        a,b=engine.devices["a"],engine.devices["b"]
        a.reference=b.reference=IDENTITY
        engine.set_processing("a","six_axis_relative")
        self.assertFalse(a.initialized)
        self.assertTrue(b.initialized)
        record=engine.ingest(sample(1,device="a"),"a")
        self.assertEqual(record["processing_profile"],"six_axis_relative")
        self.assertFalse(record["effective_magnetic_used"])
        self.assertTrue(record["processing_config_version"].startswith("attitude-v1-"))

    def test_slow_rotation_visible_when_hold_disabled_without_losing_bias(self):
        engine=BodyEngine()
        engine.ingest(sample(0),"offline")
        engine.set_processing("test","six_axis_relative")
        node=engine.devices["test"]
        node.stability.bias=(0.,0.,.2)
        node.stability.calibrated=True
        engine.set_stability("test",False)
        origin=None
        for i in range(1,1002):
            engine.ingest(sample(i,bias=(0.,0.,.4)),"offline")
            if i==1:
                origin=node.quaternion
        self.assertGreater(angle_degrees(origin,node.quaternion),1.9)
        self.assertEqual(node.stability.bias,(0.,0.,.2))

    def test_profile_validation_rejects_silent_typos(self):
        config=load_attitude_config()
        config["device_profiles"]["board"]="typo"
        with self.assertRaises(ValueError):
            validate_attitude_config(config)
        config=load_attitude_config()
        config["profiles"]["six_axis_relative"]["gravity_vector_correction"]="true"
        with self.assertRaises(ValueError):
            validate_attitude_config(config)


class PartnerDriftRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_recording_locks_processing_and_replay_retains_saved_algorithm(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=BodyRuntime(recording_dir=Path(directory))
            try:
                now=monotonic()
                runtime.consume(replace(sample(0),received_monotonic=now),"offline")
                runtime.selected_device_id="test"
                await runtime.command({"action":"set_processing","profile":"six_axis_relative"})
                await runtime.command({"action":"record_start"})
                runtime.consume(replace(sample(1),received_monotonic=now+.01),"offline")
                await runtime.tick()
                await runtime.command({"action":"set_processing","profile":"legacy_euler"})
                self.assertIn("停止",runtime.message)
                self.assertEqual(runtime.engine.devices["test"].processing_profile,"six_axis_relative")
                await runtime.command({"action":"record_stop"})
                session=runtime.recorder.session
                metadata=json.loads((runtime.recorder.folder/"metadata.json").read_text(encoding="utf-8"))
                self.assertIn("attitude_config",metadata["snapshot"])
                await runtime.command({"action":"set_processing","profile":"legacy_euler"})
                self.assertEqual(runtime.engine.devices["test"].processing_profile,"legacy_euler")
                await runtime.command({"action":"replay_open","session":session})
                self.assertEqual(runtime.payload()["devices"][0]["processing_profile"],"six_axis_relative")
                await runtime.command({"action":"set_stability","enabled":False})
                self.assertIn("回放",runtime.message)
            finally:
                await runtime.close()


if __name__=="__main__":
    unittest.main()
