import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.protocol import CurrentCsvProtocol, FrameError


ROOT = Path(__file__).resolve().parents[2]
RAW = "0,0,1,0,0,0,25,300,0,400,25"


def frame(slot="left_hand", boot="01ABCDEF", sequence=12, micros=123456):
    return f"IMU3,imu_0123456789AB,{slot},{boot},imu-body-r3,body-v1-abcd,{sequence},{micros},3,{RAW}"


class IdentityProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = CurrentCsvProtocol()

    def test_physical_identity_role_and_session_are_separate(self):
        first = self.protocol.parse(frame())
        moved = self.protocol.parse(frame("right_foot", "02ABCDEF", 0, 20))
        self.assertEqual(first.node_id, moved.node_id)
        self.assertEqual(first.body_slot, "left_hand")
        self.assertEqual(moved.body_slot, "right_foot")
        self.assertNotEqual(first.boot_id, moved.boot_id)
        self.assertEqual(first.protocol_version, "IMU3")
        self.assertEqual(first.sequence, 12)
        self.assertEqual(first.device_us, 123456)
        self.assertEqual(first.accel, (0, 0, 1))
        self.assertEqual(first.firmware_version, "imu-body-r3")
        self.assertEqual(first.config_version, "body-v1-abcd")

    def test_old_streams_do_not_claim_an_installation_role(self):
        for text in (RAW, "IMU2,imu_0123456789AB,1,10000,3," + RAW):
            sample = self.protocol.parse(text)
            self.assertIsNone(sample.body_slot)
            self.assertIsNone(sample.boot_id)
        self.assertEqual(self.protocol.parse(RAW).node_id, "right_wrist")
        self.assertEqual(self.protocol.parse(frame("unassigned")).body_slot, None)

    def test_well_formed_unknown_role_is_preserved_for_quarantine(self):
        self.assertEqual(self.protocol.parse(frame("future_segment")).body_slot, "future_segment")

    def test_malformed_metadata_and_nonfinite_values_are_rejected(self):
        bad = [frame(boot=""), frame(slot="left hand"), frame(boot="boot/1"),
               frame(sequence=-1), frame(sequence=2**32), frame(micros=2**32),
               frame().replace(",3,0,", ",4,0,"),
               frame().replace(",300,", ",nan,"), frame() + ",0",
               frame().replace("imu_0123456789AB", "id.with.dot")]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(FrameError):
                    self.protocol.parse(text)

    def test_startup_protocol_and_network_logs_are_not_samples(self):
        for line in ("[Protocol] IMU3,device_id,body_slot", "[Node] BodySlot=left_hand", "[WiFi] Connected"):
            self.assertIsNone(self.protocol.parse(line))


class NodeConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("configure_node", ROOT / "tools/configure_node.py")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.firmware = self.root / "firmware"
        (self.firmware / "include").mkdir(parents=True)
        (self.firmware / "platformio.ini").write_text("[env:custom]\nbuild_flags=-DCUSTOM=1\n")
        self.wifi = self.firmware / "include/wifi_config.h"
        self.wifi.write_text("// user-private file remains byte-identical\n")
        self.layout = self.root / "layout.json"
        self.layout.write_text(json.dumps({"schema_version": "body-layout/1", "segments": [
            {"id": "left_hand"}, {"id": "right_foot"}], "aliases_version": "historical-slots/1",
            "aliases": {"left_wrist": "left_hand"}}))

    def configure(self, role, **kwargs):
        return self.tool.configure(role, self.layout, self.firmware, **kwargs)

    def test_role_change_changes_actual_include_and_version_but_not_wifi_or_flags(self):
        original_wifi = self.wifi.read_bytes()
        original_ini = (self.firmware / "platformio.ini").read_bytes()
        one = self.configure("left_hand")
        header = Path(one["header"])
        first = header.read_bytes()
        self.assertIn(b'#define IMU_BODY_SLOT "left_hand"', first)
        self.assertFalse(self.configure("left_hand")["changed"])
        two = self.configure("right_foot")
        self.assertNotEqual(one["config_version"], two["config_version"])
        self.assertNotEqual(first, header.read_bytes())
        self.assertEqual(self.wifi.read_bytes(), original_wifi)
        self.assertEqual((self.firmware / "platformio.ini").read_bytes(), original_ini)
        main = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
        self.assertIn('#include "node_config.h"', main)

    def test_dry_run_writes_nothing(self):
        result = self.configure("left_hand", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(Path(result["header"]).exists())

    def test_alias_requires_exact_explicit_version(self):
        with self.assertRaises(ValueError):
            self.configure("left_wrist")
        result = self.configure("left_wrist", legacy_alias_version="historical-slots/1")
        self.assertEqual(result["body_slot"], "left_hand")
        self.assertEqual(result["alias_version"], "historical-slots/1")

    def test_unknown_and_unsafe_roles_fail_without_writing(self):
        for role in ("not_a_slot", 'left_hand"\n#define EVIL 1', "left wrist"):
            with self.assertRaises(ValueError):
                self.configure(role)
        self.assertFalse((self.firmware / "include/node_config.h").exists())

    def test_user_owned_existing_header_is_preserved(self):
        header = self.firmware / "include/node_config.h"
        header.write_text("// manually configured installation\n")
        with self.assertRaises(ValueError):
            self.configure("left_hand")
        self.assertEqual(header.read_text(), "// manually configured installation\n")

    def test_layout_change_changes_version_even_with_same_role(self):
        first = self.configure("left_hand")
        layout = json.loads(self.layout.read_text())
        layout["skeleton_version"] = "neutral/2"
        self.layout.write_text(json.dumps(layout))
        self.assertNotEqual(first["config_version"], self.configure("left_hand")["config_version"])


if __name__ == "__main__":
    unittest.main()
