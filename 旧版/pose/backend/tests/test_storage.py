from mocap_pose.domain.models import IngressPacket
from mocap_pose.storage.raw_session import RawSessionReader, RawSessionWriter


def test_raw_recording_round_trip(tmp_path) -> None:
    session = tmp_path / "session"
    packets = [IngressPacket(b"one", 100, "usb"), IngressPacket(b"two", 200, "ble")]
    metadata = {
        "protocol_version": 1,
        "firmware_version": "test",
        "config_version": "test",
        "nodes": [1],
    }
    with RawSessionWriter(session, metadata) as writer:
        for packet in packets:
            writer.write(packet)
    reader = RawSessionReader(session)
    assert reader.metadata == metadata
    assert list(reader.packets()) == packets
