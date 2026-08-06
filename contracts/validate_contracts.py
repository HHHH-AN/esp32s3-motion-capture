"""Validate JSON contracts and the canonical wire-protocol vector."""

from __future__ import annotations

import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    output = bytearray([0])
    code_index = 0
    code = 1
    for byte in data:
        if byte == 0:
            output[code_index] = code
            code_index = len(output)
            output.append(0)
            code = 1
        else:
            output.append(byte)
            code += 1
            if code == 0xFF:
                output[code_index] = code
                code_index = len(output)
                output.append(0)
                code = 1
    output[code_index] = code
    return bytes(output)


def validate_json_files() -> None:
    for path in sorted(ROOT.rglob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            json.load(handle)


def validate_human_profile() -> None:
    path = ROOT / "profiles" / "human-14-v1.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    assert profile["schema_version"] == 1
    assert profile["coordinate_system"] == "right-handed-x-forward-y-left-z-up"
    assert profile["root_joint_id"] == "pelvis"
    assert profile["root_node_id"] == 1
    assert profile["expected_nodes"] == list(range(1, 15))

    known_joints = {profile["root_joint_id"]}
    segment_ids: set[str] = set()
    measured_nodes = {profile["root_node_id"]}
    virtual_chest_seen = False
    for segment in profile["segments"]:
        segment_id = segment["segment_id"]
        assert segment_id not in segment_ids
        assert segment["start_joint_id"] in known_joints
        assert segment["end_joint_id"] not in known_joints
        assert segment["length_m"] > 0
        assert len(segment["direction_local"]) == 3
        assert sum(float(value) ** 2 for value in segment["direction_local"]) > 0
        node_id = segment.get("node_id")
        assert node_id is None or node_id in profile["expected_nodes"]
        if not segment["virtual"] and node_id is not None:
            measured_nodes.add(node_id)
        if segment_id == "virtual_chest":
            assert segment["virtual"] is True
            assert segment.get("orientation_source") == "pelvis"
            virtual_chest_seen = True
        segment_ids.add(segment_id)
        known_joints.add(segment["end_joint_id"])
    assert virtual_chest_seen
    assert measured_nodes == set(range(1, 15))


def validate_wire_vector() -> None:
    vector = json.loads((ROOT / "golden" / "raw-frame-v1.json").read_text(encoding="utf-8"))
    payload = vector["payload"]
    payload_bytes = struct.pack(
        "<3h3h3hhHH",
        *payload["accel_mg"],
        *payload["gyro_dps_x10"],
        *payload["mag_uT_x10"],
        payload["temperature_c_x100"],
        payload["mag_age_us"],
        payload["status_flags"],
    )
    assert len(payload_bytes) == 24
    header = struct.pack(
        "<2sBBHBIQ",
        b"MC",
        vector["protocol_version"],
        vector["message_type"],
        len(payload_bytes),
        vector["node_id"],
        vector["sequence"],
        vector["device_timestamp_us"],
    )
    body = header + payload_bytes
    crc = crc16_ccitt_false(body)
    raw = body + struct.pack("<H", crc)
    encoded = cobs_encode(raw) + b"\x00"
    assert crc == vector["crc16"]
    assert raw.hex() == vector["raw_hex"]
    assert encoded.hex() == vector["encoded_hex"]


def main() -> None:
    validate_json_files()
    validate_human_profile()
    validate_wire_vector()
    print("contracts: OK")


if __name__ == "__main__":
    main()
