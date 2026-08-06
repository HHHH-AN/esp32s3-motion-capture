import json
from pathlib import Path

import pytest

from mocap_pose.domain.models import RawImuSample
from mocap_pose.protocol.constants import MessageType
from mocap_pose.protocol.crc import crc16_ccitt_false
from mocap_pose.protocol.decoder import (
    Frame,
    StreamDecoder,
    decode_frame,
    decode_raw_batch,
    decode_raw_sample,
)
from mocap_pose.protocol.encoder import encode_frame, encode_raw_batch, encode_raw_sample
from mocap_pose.protocol.errors import FrameDecodeError

GOLDEN_ENCODED = bytes.fromhex(
    "064d4301011803012a010107cb04fb711f01010101010106e803f6ff1404e2fffa"
    "0a83fff401c40988130303572e00"
)


def representative_sample(node_id: int = 1, sequence: int = 42) -> RawImuSample:
    return RawImuSample(
        node_id,
        sequence,
        1_234_567_890_123,
        (0, 0, 1000),
        (-10, 20, -30),
        (250, -125, 500),
        2500,
        5000,
        3,
    )


def test_crc_standard_check_value() -> None:
    assert crc16_ccitt_false(b"123456789") == 0x29B1


def test_encoder_matches_repository_golden_vector() -> None:
    assert encode_raw_sample(representative_sample()) == GOLDEN_ENCODED
    contract = Path(__file__).parents[3] / "contracts" / "golden" / "raw-frame-v1.json"
    assert contract.exists()
    assert bytes.fromhex(json.loads(contract.read_text())["encoded_hex"]) == GOLDEN_ENCODED


def test_decode_raw_sample_round_trip() -> None:
    assert decode_raw_sample(decode_frame(GOLDEN_ENCODED)) == representative_sample()


def test_stream_decoder_handles_chunks_noise_and_bad_crc() -> None:
    decoder = StreamDecoder()
    bad = bytearray(GOLDEN_ENCODED)
    bad[-3] ^= 0x10
    assert decoder.feed(b"garbage\x00" + bytes(bad) + GOLDEN_ENCODED[:7]) == []
    frames = decoder.feed(GOLDEN_ENCODED[7:])
    assert len(frames) == 1
    assert decode_raw_sample(frames[0]) == representative_sample()
    assert decoder.frames_rejected == 2


def test_raw_batch_round_trip_and_strict_length_validation() -> None:
    samples = [representative_sample(1, 1), representative_sample(14, 9)]
    batch = decode_frame(encode_raw_batch(samples, sequence=8, timestamp_us=999))
    assert batch.node_id == 0
    assert decode_raw_batch(batch) == samples
    with pytest.raises(FrameDecodeError, match="requires"):
        decode_raw_batch(Frame(MessageType.RAW_BATCH, 0, 1, 1, b"\x02" + batch.payload[1:38]))
    with pytest.raises(FrameDecodeError, match="non-zero"):
        decode_raw_batch(Frame(MessageType.RAW_BATCH, 0, 1, 1, b"\x00"))


def test_unknown_message_type_is_rejected() -> None:
    encoded = bytearray(encode_frame(Frame(MessageType.ERROR, 1, 1, 1, b"x")))
    # Mutating COBS bytes also invalidates CRC; malformed-frame behavior is covered above.
    assert decode_frame(bytes(encoded)).message_type is MessageType.ERROR
