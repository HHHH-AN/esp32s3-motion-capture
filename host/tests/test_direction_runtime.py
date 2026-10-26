import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

from dashboard.body_runtime import BodyRuntime
from dashboard.body_math import angle_degrees, IDENTITY
from tests.direction_fixtures import MountCase, axis_angle, fusion_factory, make_frame, neutral_window, hinge_window, feed


class DirectionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.runtime=BodyRuntime(recording_dir=Path(self.folder.name))

    async def asyncTearDown(self):
        await self.runtime.close()
        self.folder.cleanup()

    async def test_simulation_does_not_replace_real_source_or_recorded_reference(self):
        rt=self.runtime
        node=rt.engine._device("real-device")
        node.connected=True
        node.source="real"
        await rt.command({"action":"direction_demo","scenario":"valid"})
        self.assertIn("真实设备",rt.message)
        self.assertIsNone(rt._simulation_task)
        self.assertTrue(node.connected)
        await rt.command({"action":"record_start"})
        await rt.command({"action":"direction_start","stage":"neutral","device_ids":[node.device_id]})
        self.assertIn("记录中",rt.message)
        await rt.command({"action":"record_stop"})

    async def test_windows_catalog_read_lock_cannot_leave_stale_counts(self):
        rt=self.runtime
        await rt.command({"action":"record_start"})
        await rt.tick()
        original=Path.replace
        collided=[False]
        def replace(path,target):
            if path.name=="metadata.json.tmp" and not collided[0]:
                collided[0]=True
                raise PermissionError("simulated catalog reader")
            return original(path,target)
        with patch.object(Path,"replace",replace):
            await rt.command({"action":"record_stop"})
        meta=json.loads((rt.recorder.folder/"metadata.json").read_text(encoding="utf-8"))
        self.assertTrue(collided[0])
        self.assertEqual(meta["status"],"complete")
        self.assertEqual(meta["counts"]["body_frames"],1)

    async def test_failed_capture_evidence_and_reason_are_saved_without_recording(self):
        rt=self.runtime
        await rt.command({"action":"direction_demo","scenario":"degenerate"})
        ids=[c[0] for c in rt._direction_demo.cases]
        await rt.command({"action":"direction_start","stage":"neutral","device_ids":ids})
        await asyncio.sleep(.1)
        await rt.command({"action":"direction_finish"})
        self.assertEqual(rt.engine.direction.state["status"],"failed")
        if rt._direction_save_tasks:
            await asyncio.gather(*tuple(rt._direction_save_tasks))
        path=Path(rt.engine.direction.state["saved_evidence"])
        data=json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["event"]["status"],"failed")
        self.assertTrue(data["captured_windows"]["neutral"][ids[0]])
        self.assertTrue(data["state"]["errors"])
        self.assertFalse(rt.recorder.active)

    async def test_record_and_replay_save_transforms_evidence_and_freeze_reference(self):
        rt=self.runtime
        cases=[MountCase("case-a","right_upper_arm",axis_angle((1,2,3),99),axis_angle((0,0,1),124)),
               MountCase("case-b","right_forearm",axis_angle((0,1,0),180),axis_angle((0,0,1),-81))]
        table={}
        from dashboard.body_engine import BodyEngine
        rt.engine=BodyEngine(fusion_factory=fusion_factory(table))
        now=monotonic()
        for c in cases:
            feed(rt.engine,table,[make_frame(c,time_s=now,seq=0)])
        rt.engine.direction_start("neutral",[c.device_id for c in cases],now=now)
        for i in range(341):
            for c in cases:
                feed(rt.engine,table,[make_frame(c,time_s=now+i*.01,seq=i+1)])
        rt.engine.direction_finish(now=now+3.4)
        rt.engine.direction_start("forward",now=now+3.41)
        windows=[[make_frame(c,axis_angle((0,-1,0),70),now+3.41+i*.01,342+i) for i in range(341)] for c in cases]
        for i in range(len(windows[0])):
            for frames in windows:
                feed(rt.engine,table,[frames[i]])
        rt.engine.direction_finish(now=now+6.81)
        rt.engine.direction_apply(now=now+6.81)
        await rt.command({"action":"record_start"})
        await rt.tick()
        await rt.command({"action":"reset_reference","device_id":"case-a"})
        self.assertIn("记录中",rt.message)
        self.assertTrue(rt.engine.devices["case-a"].direction_calibration["valid"])
        await rt.command({"action":"record_stop"})
        folder=rt.recorder.folder
        metadata=json.loads((folder/"metadata.json").read_text(encoding="utf-8"))
        evidence=metadata["snapshot"]["direction_calibration_evidence"]
        self.assertEqual(len(evidence["applied"]["case-a"]["forward"]),341)
        self.assertTrue(evidence["applied"]["case-a"]["selected_windows"]["forward"])
        await rt.command({"action":"replay_open","session":rt.recorder.session})
        saved=rt.payload()
        await rt.command({"action":"set_processing","device_id":"case-a","profile":"six_axis_relative"})
        self.assertIn("回放",rt.message)
        rt.engine.reset_reference("case-a")
        restored=rt.payload()
        self.assertEqual(restored["direction_calibration"],saved["direction_calibration"])
        self.assertTrue(restored["devices"][0]["direction_calibration"]["valid"])
        await rt.command({"action":"replay_close"})
        self.assertFalse(rt.payload()["devices"][0]["direction_calibration"]["valid"])
