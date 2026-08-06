import time

from fastapi.testclient import TestClient

from mocap_pose.api.app import create_app
from mocap_pose.api.schemas import PoseFrameMessage
from mocap_pose.config.settings import Settings
from mocap_pose.sources.mock_source import MockSource


def test_mock_source_reaches_pose_websocket(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(Settings(expected_nodes=(1,)), MockSource())
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.post("/api/devices/scan").json()[0]["id"] == "mock-bridge"
        assert client.post("/api/devices/connect", json={"id": "mock-bridge"}).status_code == 204
        assert client.post("/api/calibration/mounting").status_code == 501
        assert client.post("/api/record/start").status_code == 204
        assert client.post("/api/record/stop").status_code == 204
        assert list((tmp_path / "recordings").glob("session_*"))
        assert client.post("/api/playback/speed", json={"speed": 2}).status_code == 409
        with client.websocket_connect("/ws/pose") as socket:
            message = socket.receive_json()
            assert message["type"] == "pose.frame.v1"
            assert message["schema_version"] == 1
            assert message["node_id"] == 1
            assert len(message["quaternion_wxyz"]) == 4
            assert PoseFrameMessage.model_validate(message).schema_version == 1


def test_pose_websocket_selects_one_node_and_is_limited_to_render_rate() -> None:
    app = create_app(Settings(expected_nodes=(1, 2)), MockSource(node_ids=(1, 2)))
    with TestClient(app) as client:
        with client.websocket_connect("/ws/pose?node_id=2") as socket:
            first = socket.receive_json()
            started = time.monotonic()
            messages = [socket.receive_json() for _ in range(9)]
            elapsed = time.monotonic() - started
    assert first["node_id"] == 2
    assert all(message["node_id"] == 2 for message in messages)
    assert elapsed >= 0.12
