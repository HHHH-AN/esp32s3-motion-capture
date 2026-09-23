import struct

from mocap_pose.sources.ble_fragments import BleFragmentReassembler


def fragment(frame_id: int, index: int, count: int, total: int, payload: bytes) -> bytes:
    return struct.pack("<HBBH", frame_id, index, count, total) + payload


def test_ble_fragments_reassemble_out_of_order() -> None:
    reassembler = BleFragmentReassembler()
    assert reassembler.push(fragment(7, 1, 2, 6, b"def"), 100) is None
    assert reassembler.push(fragment(7, 0, 2, 6, b"abc"), 110) == b"abcdef"
    assert reassembler.completed_frames == 1


def test_duplicate_invalid_and_timeout_discard_whole_frame() -> None:
    reassembler = BleFragmentReassembler(timeout_us=10)
    first = fragment(1, 0, 2, 6, b"abc")
    assert reassembler.push(first, 100) is None
    assert reassembler.push(first, 101) is None
    assert reassembler.duplicate_frames == 1
    assert reassembler.push(fragment(2, 0, 2, 6, b"abc"), 200) is None
    assert reassembler.push(fragment(3, 0, 1, 3, b"xyz"), 220) == b"xyz"
    assert reassembler.timed_out_frames == 1


def test_inconsistent_header_and_total_length_are_rejected() -> None:
    reassembler = BleFragmentReassembler()
    assert reassembler.push(fragment(1, 0, 2, 6, b"abc"), 1) is None
    assert reassembler.push(fragment(1, 1, 3, 6, b"def"), 2) is None
    assert reassembler.invalid_frames == 1
    assert reassembler.push(fragment(2, 0, 1, 7, b"short"), 3) is None
    assert reassembler.invalid_frames == 2
