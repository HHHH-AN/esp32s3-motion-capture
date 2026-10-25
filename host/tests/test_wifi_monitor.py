import json
from pathlib import Path
import socket
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from dashboard.coordinates import CoordinateSettings
from run_wifi_monitor import WifiNode, handler_for, parse_nodes


def frame(sequence, device_us=None, node_id="imu_test", gyro=0):
    device_us = sequence*10000 if device_us is None else device_us
    return f"IMU2,{node_id},{sequence},{device_us},3,0,0,1,0,0,{gyro},25,30,0,10,0".encode()


def vector_frame(sequence, gyro, node_id="imu_test", flags=3, device_us=None):
    device_us = sequence*10000 if device_us is None else device_us
    gx, gy, gz = gyro
    return (f"IMU2,{node_id},{sequence},{device_us},{flags},0,0,1,"
            f"{gx},{gy},{gz},25,300,0,100,0").encode()


class WifiMonitorTests(unittest.TestCase):
    def node(self, slot="A"):
        return WifiNode(slot, "127.0.0.1", 9000, CoordinateSettings())

    def calibrated_node(self, slot="A", bias=(3., -.7, 6.)):
        node = self.node(slot)
        node_id = "imu_"+slot
        # Advance sample timestamps deterministically without sleeping. The
        # production calibrate() entry point must still accept an online node.
        start = time.monotonic()
        node.connected = True
        node.consume(vector_frame(0, bias, node_id), start)
        self.assertTrue(node.calibrate())
        for sequence in range(1, 402):
            node.consume(vector_frame(sequence, bias, node_id), start+sequence*.01)
        state = node.snapshot()["stability"]
        self.assertTrue(state["calibrated"])
        self.assertFalse(state["calibrating"])
        for actual, expected in zip(state["gyro_bias_dps"], bias):
            self.assertAlmostEqual(actual, expected, places=9)
        return node, node_id, start, 402

    def test_stream_identity_and_sequence_quality(self):
        node = self.node()
        node.consume(frame(1), 1)
        node.consume(frame(1), 1.01)
        node.consume(frame(4), 1.04)
        node.consume(frame(5, node_id="wrong_device"), 1.05)
        data = node.snapshot()
        self.assertEqual(data["frames"], 2)
        self.assertEqual(data["missing_frames"], 2)
        self.assertEqual(data["duplicate_frames"], 1)
        self.assertEqual(data["invalid_frames"], 1)

    def test_nodes_keep_independent_fusion_and_zero_reference(self):
        a, b = self.node("A"), self.node("B")
        now = time.monotonic()
        for i in range(50):
            a.consume(frame(i, gyro=90), now+i*.01)
            b.consume(frame(i, node_id="second"), now+i*.01)
        a.connected = b.connected = True
        self.assertGreater(abs(a.snapshot()["euler_deg"][2]), 35)
        self.assertLess(abs(b.snapshot()["euler_deg"][2]), .01)
        self.assertTrue(a.zero())
        self.assertLess(abs(a.snapshot()["euler_deg"][2]), .01)
        self.assertEqual(b.snapshot()["node_id"], "second")

    def test_reboot_reinitializes_but_sampling_gap_only_increments_gap_counter(self):
        node = self.node()
        node.consume(frame(100), 1)
        node.consume(frame(0), 1.01)
        self.assertEqual(node.snapshot()["attitude_reinitializations"], 1)
        node.consume(frame(1, device_us=500000), 1.5)
        self.assertEqual(node.snapshot()["attitude_reinitializations"], 1)
        self.assertEqual(node.snapshot()["sampling_gaps"], 1)

    def test_calibrated_nodes_rotate_then_hold_independently(self):
        bias_a, bias_b = (3., -.7, 6.), (-.5, .2, -1.5)
        a, id_a, time_a, next_a = self.calibrated_node("A", bias_a)
        b, id_b, time_b, next_b = self.calibrated_node("B", bias_b)
        for i in range(100):
            sequence = next_a+i
            turning = (bias_a[0], bias_a[1], bias_a[2]+90.)
            a.consume(vector_frame(sequence, turning, id_a, flags=1), time_a+sequence*.01)
            sequence_b = next_b+i
            b.consume(vector_frame(sequence_b, bias_b, id_b), time_b+sequence_b*.01)
        self.assertGreater(a.snapshot()["euler_deg"][2], 80.)
        self.assertTrue(b.snapshot()["stability"]["holding"])
        self.assertFalse(a.snapshot()["stability"]["holding"])
        for i in range(100, 280):
            sequence = next_a+i
            a.consume(vector_frame(sequence, bias_a, id_a, flags=1), time_a+sequence*.01)
            sequence_b = next_b+i
            b.consume(vector_frame(sequence_b, bias_b, id_b), time_b+sequence_b*.01)
        held_a, held_b = a.snapshot(), b.snapshot()
        self.assertTrue(held_a["stability"]["holding"])
        self.assertTrue(held_b["stability"]["holding"])
        self.assertNotEqual(held_a["quaternion"], held_b["quaternion"])
        for i in range(280, 480):
            sequence = next_a+i
            a.consume(vector_frame(sequence, bias_a, id_a, flags=1), time_a+sequence*.01)
            sequence_b = next_b+i
            b.consume(vector_frame(sequence_b, bias_b, id_b), time_b+sequence_b*.01)
        for node, before in ((a, held_a), (b, held_b)):
            self.assertTrue(node.snapshot()["stability"]["holding"])
            for actual, expected in zip(node.snapshot()["quaternion"], before["quaternion"]):
                self.assertAlmostEqual(actual, expected, places=12)
        turning = (bias_a[0], bias_a[1], bias_a[2]+1.)
        sequence = next_a+480
        a.consume(vector_frame(sequence, turning, id_a, flags=1), time_a+sequence*.01)
        resumed = a.snapshot()
        self.assertFalse(resumed["stability"]["holding"])
        self.assertAlmostEqual(resumed["stability"]["corrected_gyro_dps"][2], 1.)
        self.assertGreater(resumed["euler_deg"][2]-held_a["euler_deg"][2], .005)
        self.assertTrue(b.snapshot()["stability"]["holding"])

    def test_disabling_hold_keeps_bias_compensation_active(self):
        bias = (3., -.7, 6.)
        node, node_id, start, next_sequence = self.calibrated_node(bias=bias)
        for i in range(100):
            sequence = next_sequence+i
            node.consume(vector_frame(sequence, bias, node_id, flags=1), start+sequence*.01)
        self.assertTrue(node.snapshot()["stability"]["holding"])
        before = node.snapshot()["quaternion"]
        node.set_stability(False)
        self.assertFalse(node.snapshot()["stability"]["holding"])
        for i in range(100, 300):
            sequence = next_sequence+i
            node.consume(vector_frame(sequence, bias, node_id, flags=1), start+sequence*.01)
        state = node.snapshot()
        self.assertFalse(state["stability"]["enabled"])
        self.assertFalse(state["stability"]["holding"])
        self.assertTrue(state["stability"]["calibrated"])
        for value in state["stability"]["corrected_gyro_dps"]:
            self.assertAlmostEqual(value, 0., places=9)
        for actual, expected in zip(state["quaternion"], before):
            self.assertAlmostEqual(actual, expected, places=10)

    def test_same_device_sequence_and_clock_restart_clear_calibration(self):
        node, node_id, start, next_sequence = self.calibrated_node()
        node.consume(vector_frame(0, (3., -.7, 6.), node_id, device_us=0),
                     start+next_sequence*.01)
        state = node.snapshot()
        self.assertFalse(state["stability"]["calibrated"])
        self.assertEqual(state["stability"]["gyro_bias_dps"], (0., 0., 0.))
        self.assertEqual(state["attitude_reinitializations"], 1)

    def test_device_clock_rollback_clears_bias_even_when_sequence_continues(self):
        node, node_id, start, next_sequence = self.calibrated_node()
        node.consume(vector_frame(next_sequence, (3., -.7, 6.), node_id, device_us=0),
                     start+next_sequence*.01)
        state = node.snapshot()
        self.assertEqual(state["node_id"], node_id)
        self.assertEqual(state["sequence"], next_sequence)
        self.assertFalse(state["stability"]["calibrated"])
        self.assertEqual(state["stability"]["gyro_bias_dps"], (0., 0., 0.))
        self.assertEqual(state["attitude_reinitializations"], 1)
        self.assertEqual(state["sampling_gaps"], 0)

    def test_reconnect_keeps_bias_only_when_same_device_clock_continues(self):
        for restarted in (False, True):
            with self.subTest(restarted=restarted):
                node, node_id, start, next_sequence = self.calibrated_node()
                old_bias = node.snapshot()["stability"]["gyro_bias_dps"]
                # Reproduce _receive()'s reconnect handoff without opening a
                # physical socket or depending on reconnection scheduling.
                node.previous_connection = (node.node_id, node.last_sequence, node.last_device_us)
                node.node_id = None
                node.reset_attitude()
                sequence = 0 if restarted else next_sequence
                node.consume(vector_frame(sequence, (3., -.7, 6.), node_id),
                             start+next_sequence*.01)
                state = node.snapshot()["stability"]
                self.assertEqual(state["calibrated"], not restarted)
                self.assertFalse(state["holding"])
                self.assertEqual(state["gyro_bias_dps"], (0., 0., 0.) if restarted else old_bias)

    def test_sampling_gap_keeps_calibrated_rotated_pose_without_jump(self):
        bias = (3., -.7, 6.)
        node, node_id, start, next_sequence = self.calibrated_node(bias=bias)
        for i in range(50):
            sequence = next_sequence+i
            gyro = (bias[0], bias[1], bias[2]+90.)
            node.consume(vector_frame(sequence, gyro, node_id, flags=1), start+sequence*.01)
        for i in range(50, 180):
            sequence = next_sequence+i
            node.consume(vector_frame(sequence, bias, node_id, flags=1), start+sequence*.01)
        before = node.snapshot()
        self.assertTrue(before["stability"]["holding"])
        self.assertGreater(abs(before["euler_deg"][2]), 40.)
        sequence = next_sequence+180
        device_us = node.last_device_us+500000
        node.consume(vector_frame(sequence, bias, node_id, flags=1, device_us=device_us),
                     node.latest+.5)
        after = node.snapshot()
        self.assertEqual(after["sampling_gaps"], before["sampling_gaps"]+1)
        self.assertAlmostEqual(after["last_gap_s"], .5)
        self.assertEqual(after["attitude_reinitializations"], before["attitude_reinitializations"])
        self.assertTrue(after["stability"]["calibrated"])
        self.assertFalse(after["stability"]["holding"])
        self.assertEqual(after["stability"]["gyro_bias_dps"], before["stability"]["gyro_bias_dps"])
        for actual, expected in zip(after["quaternion"], before["quaternion"]):
            self.assertAlmostEqual(actual, expected, places=10)

    def test_http_calibrate_and_stability_only_change_selected_online_slot(self):
        a, b = self.node("A"), self.node("B")
        now = time.monotonic()
        for node, node_id in ((a, "imu_first"), (b, "imu_second")):
            node.connected = True
            node.consume(vector_frame(0, (0., 0., 0.), node_id), now)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for({"A": a, "B": b}))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        def post(path, payload):
            request = Request(base_url+path, data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=2) as response:
                self.assertTrue(json.load(response)["ok"])

        try:
            post("/api/calibrate", {"slot": "A"})
            self.assertTrue(a.snapshot()["stability"]["calibrating"])
            self.assertFalse(b.snapshot()["stability"]["calibrating"])
            post("/api/stability", {"slot": "B", "enabled": False})
            self.assertTrue(a.snapshot()["stability"]["enabled"])
            self.assertFalse(b.snapshot()["stability"]["enabled"])
            b.connected = False
            with self.assertRaises(HTTPError) as offline:
                post("/api/calibrate", {"slot": "B"})
            self.assertEqual(offline.exception.code, 409)
            self.assertFalse(b.stability.calibrating)
            a.latest = time.monotonic()-2.
            with self.assertRaises(HTTPError) as stale:
                post("/api/calibrate", {"slot": "A"})
            self.assertEqual(stale.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(3)

    def test_offline_or_unconfigured_node_cannot_be_faked_online(self):
        node = self.node()
        self.assertFalse(node.snapshot()["valid"])
        self.assertFalse(node.zero())
        node.connected = True
        node.consume(frame(0), time.monotonic()-2)
        self.assertFalse(node.snapshot()["valid"])
        self.assertFalse(node.zero())

    def test_endpoint_configuration_cannot_duplicate_a_device(self):
        self.assertEqual(parse_nodes(["A=192.168.4.1:9000"]), {"A": ("192.168.4.1", 9000)})
        for bad in (["A=x:9000", "B=x:9000"], ["D=x:9000"], ["A=x:0"]):
            with self.assertRaises(ValueError):
                parse_nodes(bad)

    def test_real_local_tcp_stream_reaches_http_api(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        release = threading.Event()

        def device():
            connection, _ = listener.accept()
            with connection:
                for i in range(10):
                    connection.sendall(frame(i)+b"\n")
                    time.sleep(.01)
                release.wait(3)

        sender = threading.Thread(target=device, daemon=True)
        sender.start()
        node = WifiNode("A", "127.0.0.1", listener.getsockname()[1], CoordinateSettings())
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for({"A": node}))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        node.start()
        try:
            deadline = time.monotonic()+3
            while node.snapshot()["frames"] < 10 and time.monotonic() < deadline:
                time.sleep(.02)
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/status", timeout=2) as response:
                data = json.load(response)
            self.assertTrue(data["nodes"]["A"]["valid"])
            self.assertEqual(data["nodes"]["A"]["frames"], 10)
            self.assertEqual(set(data["nodes"]), {"A"})
            self.assertFalse(data["position_integration"])
            self.assertEqual(data["source"], "real_wifi_tcp")
        finally:
            node.stop.set()
            release.set()
            server.shutdown()
            server.server_close()
            listener.close()
            node.thread.join(4)
            sender.join(4)
            worker.join(4)

    def test_two_tcp_devices_keep_independent_live_http_states(self):
        release, transmit = threading.Event(), threading.Event()
        listeners, senders, accepted = [], [], []
        nodes = {}
        streams = {
            "A": ("imu_first", list(range(60)), 90),
            "B": ("imu_second", [i for i in range(100, 141) if i != 120], -45),
        }

        def device(listener, ready, slot):
            connection, _ = listener.accept()
            with connection:
                ready.set()
                if not transmit.wait(3):
                    return
                node_id, sequences, gyro = streams[slot]
                for sequence in sequences:
                    data = frame(sequence, node_id=node_id, gyro=gyro)+b"\n"
                    # A has a duplicate; B has one missing sequence. Neither
                    # quality counter may leak into the other endpoint.
                    connection.sendall(data)
                    if slot == "A" and sequence == 29:
                        connection.sendall(data)
                release.wait(10)

        for slot in streams:
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(3)
            listeners.append(listener)
            ready = threading.Event()
            accepted.append(ready)
            sender = threading.Thread(target=device, args=(listener, ready, slot), daemon=True)
            senders.append(sender)
            sender.start()
            nodes[slot] = WifiNode(slot, "127.0.0.1", listener.getsockname()[1], CoordinateSettings())

        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(nodes))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        for node in nodes.values():
            node.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        def status():
            with urlopen(base_url+"/api/status", timeout=2) as response:
                return json.load(response)

        try:
            self.assertTrue(all(ready.wait(3) for ready in accepted))
            transmit.set()
            deadline = time.monotonic()+3
            while time.monotonic() < deadline:
                if all(nodes[slot].snapshot()["frames"] == len(stream[1])
                       for slot, stream in streams.items()):
                    break
                time.sleep(.01)
            data = status()
            self.assertEqual(set(data["nodes"]), {"A", "B"})
            self.assertEqual(data["source"], "real_wifi_tcp")
            self.assertFalse(data["position_integration"])
            a, b = data["nodes"]["A"], data["nodes"]["B"]
            for state, node_id, frames, sequence in (
                    (a, "imu_first", 60, 59), (b, "imu_second", 40, 140)):
                self.assertTrue(state["connected"])
                self.assertTrue(state["valid"])
                self.assertEqual(state["node_id"], node_id)
                self.assertEqual(state["frames"], frames)
                self.assertEqual(state["sequence"], sequence)
                self.assertEqual(state["invalid_frames"], 0)
            self.assertNotEqual(a["endpoint"], b["endpoint"])
            self.assertEqual((a["duplicate_frames"], b["duplicate_frames"]), (1, 0))
            self.assertEqual((a["missing_frames"], b["missing_frames"]), (0, 1))
            self.assertGreater(a["euler_deg"][2], 40)
            self.assertLess(b["euler_deg"][2], -10)
            self.assertNotEqual(a["quaternion"], b["quaternion"])

            request = Request(base_url+"/api/zero", data=b'{"slot":"A"}',
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=2) as response:
                self.assertTrue(json.load(response)["ok"])
            after_zero = status()["nodes"]
            self.assertEqual(after_zero["A"]["quaternion"], [1., 0., 0., 0.])
            self.assertEqual(after_zero["B"]["quaternion"], b["quaternion"])
            self.assertEqual(after_zero["B"]["frames"], b["frames"])
            self.assertTrue(after_zero["A"]["valid"])
            self.assertTrue(after_zero["B"]["valid"])
        finally:
            for node in nodes.values():
                node.stop.set()
            transmit.set()
            release.set()
            server.shutdown()
            server.server_close()
            for listener in listeners:
                listener.close()
            for node in nodes.values():
                node.thread.join(4)
            for sender in senders:
                sender.join(4)
            worker.join(4)


if __name__ == "__main__":
    unittest.main()
