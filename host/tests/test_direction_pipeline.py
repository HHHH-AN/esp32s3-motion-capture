"""Functional mounting calibration through actual registry/processing/solver.

Only the AHRS reference output is supplied as known truth. Every sample still
passes NodeProcessor, per-device quality/session handling, the guided capture,
the fitter and the normal world-to-local hierarchical solver. These are
offline geometric regressions, not physical angle or heading certification.
"""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.body_engine import BodyEngine
from dashboard.body_math import IDENTITY, angle_degrees, inverse, multiply, rotate
from dashboard.body_recording import BodyRecorder, BodyReplay
from tests.direction_fixtures import (MountCase, TruthFrame, axis_angle, feed,
                                      fusion_factory, hinge_window, make_frame,
                                      neutral_window, register_truth)


def segment(state,slot):
    return next(item for item in state["body_frame"]["segments"] if item["id"]==slot)


class FunctionalDirectionPipelineTests(unittest.TestCase):
    def build(self,mount_a=IDENTITY,mount_b=IDENTITY,fusion_a=None,fusion_b=None):
        self.cases = [MountCase("fixture_upper","right_upper_arm",mount_a,
                               fusion_a or axis_angle((0,0,1),146.6)),
                      MountCase("fixture_fore","right_forearm",mount_b,
                               fusion_b or axis_angle((0,0,1),-107.3))]
        self.table = {}
        self.input_source = "simulation_sensor_truth"
        self.engine = BodyEngine(fusion_factory=fusion_factory(self.table))
        self.seq = 0
        self.now = 99.99
        for case in self.cases:
            feed(self.engine,self.table,[make_frame(case,time_s=self.now,seq=0)])
        return self.engine

    def ingest_windows(self,windows):
        for frames in windows:
            register_truth(self.table,frames)
        for i in range(max(map(len,windows))):
            for frames in windows:
                if i < len(frames):
                    frame = frames[i]
                    self.engine.ingest(frame.sample,"fixture-"+frame.sample.node_id,
                                       self.input_source)
                    self.now = max(self.now,frame.sample.received_monotonic)
                    self.seq = max(self.seq,frame.sample.sequence)

    def capture_neutral(self):
        self.engine.direction_start("neutral",[c.device_id for c in self.cases],now=100.)
        self.ingest_windows([neutral_window(c,start=100.,duration=3.4,first_sequence=1) for c in self.cases])
        self.engine.direction_finish(now=self.now)
        return self.engine.snapshot(self.now)["direction_calibration"]

    def capture_forward(self,*,axis=(0.,-1.,0.),peak=70.,duration=4.,drift=0.):
        start = self.now+.01
        first_seq = self.seq+1
        # Move before sampling; capture only the stopped endpoint.
        travel = [hinge_window(c,start=start,duration=duration,axis=axis,
                               peak_deg=peak,first_sequence=first_seq) for c in self.cases]
        self.ingest_windows([frames[:len(frames)//2+1] for frames in travel])
        start,first_seq = self.now+.01,self.seq+1
        self.engine.direction_start("forward",now=start)
        windows = [[make_frame(c,axis_angle(axis,peak),start+i*.01,first_seq+i)
                    for i in range(341)] for c in self.cases]
        if drift:
            windows = [[replace(frame,quaternion=multiply(axis_angle((0,0,1),drift*i/(len(frames)-1)),
                                                         frame.quaternion))
                        for i,frame in enumerate(frames)] for frames in windows]
        self.ingest_windows(windows)
        self.engine.direction_finish(now=self.now)
        return self.engine.snapshot(self.now)["direction_calibration"]

    def calibrate(self):
        self.assertEqual(self.capture_neutral()["status"],"neutral_ready")
        self.assertEqual(self.capture_forward()["status"],"candidate")
        self.engine.direction_apply(now=self.now)
        self.assertEqual(self.engine.snapshot(self.now)["direction_calibration"]["status"],"complete")

    def held_pose(self,upper,forearm):
        windows = []
        for case,q in zip(self.cases,(upper,forearm)):
            windows.append([make_frame(case,q,self.now+.01+i*.01,self.seq+1+i)
                            for i in range(15)])
        self.ingest_windows(windows)
        return self.engine.snapshot(self.now)

    def assertRotation(self,actual,expected,tolerance=1e-6):
        self.assertLess(angle_degrees(actual,expected),tolerance)

    def test_static_neutral_alone_zeros_but_retains_unknown_heading_conjugation(self):
        engine = self.build()
        engine.begin_initialization([c.device_id for c in self.cases],now=100.)
        engine.finish_initialization(now=100.)
        self.ingest_windows([neutral_window(c,start=100.,first_sequence=1) for c in self.cases])
        neutral = engine.snapshot(self.now)
        self.assertEqual(neutral["initialization"]["status"],"complete")
        self.assertRotation(segment(neutral,"right_upper_arm")["world_quaternion"],IDENTITY)
        self.assertRotation(segment(neutral,"right_forearm")["world_quaternion"],IDENTITY)
        expected = axis_angle((0,-1,0),60)
        wrong = self.held_pose(expected,expected)
        self.assertGreater(angle_degrees(segment(wrong,"right_upper_arm")["world_quaternion"],expected),50)
        self.assertGreater(angle_degrees(segment(wrong,"right_forearm")["world_quaternion"],expected),50)
        self.assertGreater(angle_degrees(segment(wrong,"right_upper_arm")["world_quaternion"],
                                         segment(wrong,"right_forearm")["world_quaternion"]),50)

    def test_fixed_mounts_and_different_reference_yaws_recover_held_out_directions(self):
        installations = [(IDENTITY,IDENTITY),
                         (axis_angle((0,0,1),90),axis_angle((1,0,0),180)),
                         (axis_angle((1,2,3),113),axis_angle((-2,.3,1),71))]
        for mount_a,mount_b in installations:
            with self.subTest(mount_a=mount_a,mount_b=mount_b):
                self.build(mount_a,mount_b)
                self.calibrate()
                for axis,angle in [((0,-1,0),42),((-1,0,0),56),((.4,-.2,.8),37)]:
                    truth = axis_angle(axis,angle)
                    frame = self.held_pose(truth,truth)
                    a,b = segment(frame,"right_upper_arm"),segment(frame,"right_forearm")
                    self.assertRotation(a["world_quaternion"],truth)
                    self.assertRotation(b["world_quaternion"],truth)
                    self.assertRotation(b["local_quaternion"],IDENTITY)
                    # Missing hand has no self-generated local action.
                    self.assertFalse(segment(frame,"right_hand")["measured"])
                    self.assertRotation(segment(frame,"right_hand")["local_quaternion"],IDENTITY)
                    self.assertRotation(segment(frame,"right_hand")["world_quaternion"],truth)
                    if axis==(0,-1,0):
                        self.assertGreater(a["end"][0]-a["start"][0],0)
                    elif axis==(-1,0,0):
                        self.assertLess(a["end"][1]-a["start"][1],0)

    def test_independent_elbow_and_parent_rotation_are_not_double_applied(self):
        self.build(axis_angle((1,2,3),83),axis_angle((1,-1,.4),142))
        self.calibrate()
        upper = axis_angle((0,-1,0),35)
        local_elbow = axis_angle((0,-1,0),47)
        fore = multiply(upper,local_elbow)
        state = self.held_pose(upper,fore)
        self.assertRotation(segment(state,"right_upper_arm")["world_quaternion"],upper)
        self.assertRotation(segment(state,"right_forearm")["world_quaternion"],fore)
        self.assertRotation(segment(state,"right_forearm")["local_quaternion"],local_elbow)
        # A rotates while the forearm stays fixed in the world.
        state = self.held_pose(axis_angle((-1,0,0),58),IDENTITY)
        self.assertRotation(segment(state,"right_forearm")["world_quaternion"],IDENTITY)
        self.assertRotation(segment(state,"right_forearm")["local_quaternion"],
                            inverse(segment(state,"right_upper_arm")["world_quaternion"]))

    def test_degenerate_hinge_parallel_to_gravity_is_rejected(self):
        self.build()
        self.capture_neutral()
        state = self.capture_forward(axis=(0,0,1))
        self.assertEqual(state["status"],"failed")
        self.assertFalse(any(node.direction_calibration for node in self.engine.devices.values()))

    def test_insufficient_excursion_and_reference_drift_do_not_report_success(self):
        for peak,drift in [(3.,0.),(70.,22.)]:
            with self.subTest(peak=peak,drift=drift):
                self.build()
                self.capture_neutral()
                result = self.capture_forward(peak=peak,drift=drift)
                self.assertEqual(result["status"],"failed")
                self.assertFalse(any(node.direction_calibration for node in self.engine.devices.values()))

    def test_disconnect_during_capture_requires_reacquisition(self):
        self.build()
        self.engine.direction_start("neutral",[c.device_id for c in self.cases],now=100.)
        self.ingest_windows([neutral_window(c,start=100.,duration=.5,first_sequence=1) for c in self.cases])
        self.engine.disconnect_endpoint("fixture-"+self.cases[0].device_id)
        try:
            self.engine.direction_finish(now=self.now)
        except ValueError:
            pass
        self.assertEqual(self.engine.snapshot(self.now)["direction_calibration"]["status"],"failed")

    def test_low_resolution_host_arrivals_use_actual_device_clock(self):
        self.build()
        def rounded(windows):
            return [[replace(f,sample=replace(f.sample,received_monotonic=round(f.sample.received_monotonic*64)/64))
                     for f in frames] for frames in windows]
        self.engine.direction_start("neutral",[c.device_id for c in self.cases],now=100.)
        self.ingest_windows(rounded([neutral_window(c,start=100.,duration=3.4,first_sequence=1) for c in self.cases]))
        self.assertEqual(self.engine.direction_finish(now=self.now)["status"],"neutral_ready")
        start=self.now+.02
        self.engine.direction_start("forward",now=start)
        self.ingest_windows(rounded([[make_frame(c,axis_angle((0,-1,0),70),start+i*.01,self.seq+1+i) for i in range(341)] for c in self.cases]))
        result=self.engine.direction_finish(now=self.now)
        self.assertEqual(result["status"],"candidate",result.get("message"))
        self.assertEqual(len(self.engine.direction.motion[self.cases[0].device_id]),341)

    def test_invalid_sample_or_mode_change_during_window_rejects(self):
        for change in ("badframe","mode","insufficient"):
            with self.subTest(change=change):
                self.build()
                self.engine.direction_start("neutral",[c.device_id for c in self.cases],now=100.)
                self.ingest_windows([neutral_window(c,start=100.,duration=.1,first_sequence=1) for c in self.cases])
                if change=="badframe":
                    self.engine.invalid_frame("fixture-"+self.cases[0].device_id,"invalid")
                elif change=="mode":
                    self.engine.set_processing(self.cases[0].device_id,"six_axis_relative")
                result=self.engine.direction_finish(now=self.now)
                self.assertEqual(result["status"],"failed")
                with self.assertRaises(ValueError):
                    self.engine.direction_start("forward",now=self.now)

    def test_bent_elbow_in_straight_arm_capture_is_not_accepted(self):
        self.build()
        self.capture_neutral()
        start=self.now+.01
        self.engine.direction_start("forward",now=start)
        self.ingest_windows([[make_frame(c,axis_angle((0,-1,0),peak),start+i*.01,self.seq+1+i) for i in range(341)]
                             for c,peak in zip(self.cases,(70.,30.))])
        state=self.engine.direction_finish(now=self.now)
        self.assertEqual(state["status"],"failed")
        self.assertIn("保持肘伸直",state["message"])
        self.assertFalse(any(d.direction_calibration for d in self.engine.devices.values()))

    def test_rewear_mode_change_and_reboot_invalidate_saved_installation(self):
        for change in ("rewear","mode","reboot"):
            with self.subTest(change=change):
                self.build()
                self.calibrate()
                device = self.cases[0].device_id
                if change=="rewear":
                    self.engine.bind(device,"right_upper_arm",override=True)
                elif change=="mode":
                    self.engine.set_processing(device,"six_axis_relative")
                else:
                    frame = make_frame(self.cases[0],time_s=self.now+.01,seq=0,boot="second-boot")
                    feed(self.engine,self.table,[frame])
                node = self.engine.devices[device]
                self.assertFalse(node.direction_calibration["valid"])
                self.assertTrue(node.direction_calibration["invalid_reason"])
                self.assertFalse(node.initialized)
                self.assertRotation(node.fusion_to_world,IDENTITY)

    def test_recording_replay_preserves_calibration_and_actual_saved_body_frames(self):
        self.build(axis_angle((1,0,0),90),axis_angle((1,2,-3),125))
        self.calibrate()
        forward = axis_angle((0,-1,0),52)
        saved = self.held_pose(forward,multiply(forward,axis_angle((0,-1,0),30)))
        with tempfile.TemporaryDirectory() as directory:
            recorder = BodyRecorder(Path(directory))
            session = recorder.start(saved)
            recorder.append_body_frame(saved)
            recorder.stop()
            metadata = json.loads((Path(directory)/session/"metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["snapshot"]["direction_calibration"]["status"],"complete")
            replay = BodyReplay(Path(directory))
            try:
                replay.open(session)
                restored = replay.frame()
                self.assertEqual(restored["direction_calibration"],json.loads(json.dumps(saved["direction_calibration"])))
                self.assertRotation(segment(restored,"right_forearm")["world_quaternion"],
                                    segment(saved,"right_forearm")["world_quaternion"])
                self.engine.reset_reference(self.cases[0].device_id)
                self.assertEqual(replay.frame(),restored)
            finally:
                replay.close()

    def test_production_fusion_raw_samples_different_modes_and_mounts(self):
        """No supplied Q: run raw observations through the real AHRS as well."""
        for profiles in (("six_axis_relative","six_axis_relative"),
                         ("magnetic_guarded","magnetic_guarded"),
                         ("six_axis_relative","magnetic_guarded")):
            with self.subTest(profiles=profiles):
                self.build(axis_angle((1,2,3),63),axis_angle((1,0,0),180))
                self.engine=BodyEngine()
                self.input_source="simulation_sensor"
                self.seq,self.now=0,99.99
                for case,profile in zip(self.cases,profiles):
                    frame=make_frame(case,time_s=self.now,seq=0)
                    self.engine.ingest(frame.sample,"fixture-"+case.device_id,"simulation_sensor")
                    self.engine.set_processing(case.device_id,profile)
                    self.engine.set_stability(case.device_id,False)
                self.calibrate()
                # The second capture ends at a raised arm. Physically lower it
                # with matching gyro observations before independent actions;
                # an instantaneous pose jump is not valid raw IMU input.
                lower = [hinge_window(c,start=self.now-2.,first_sequence=self.seq-200,
                                      peak_deg=70.)[201:] for c in self.cases]
                self.ingest_windows(lower)
                # Smooth new actions, independent of the fitted front raise.
                start,seq=self.now+.01,self.seq+1
                self.ingest_windows([hinge_window(c,start=start,first_sequence=seq,axis=(-1,0,0),peak_deg=50) for c in self.cases])
                state=self.engine.snapshot(self.now)
                for role in ("right_upper_arm","right_forearm"):
                    self.assertLess(angle_degrees(segment(state,role)["world_quaternion"],IDENTITY),2.)
                # Inspect side-raise peak through a second fresh action window.
                windows=[hinge_window(c,start=self.now+.01,first_sequence=self.seq+1,axis=(-1,0,0),peak_deg=50) for c in self.cases]
                midpoint=len(windows[0])//2
                self.ingest_windows([w[:midpoint+1] for w in windows])
                peak=self.engine.snapshot(self.now)
                for role in ("right_upper_arm","right_forearm"):
                    bone=segment(peak,role)
                    self.assertLess(bone["end"][1]-bone["start"][1],-.1)
                    self.assertLess(angle_degrees(bone["world_quaternion"],axis_angle((-1,0,0),50)),3.)


if __name__=="__main__":
    unittest.main()
