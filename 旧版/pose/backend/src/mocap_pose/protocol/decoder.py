from __future__ import annotations

import struct
from dataclasses import dataclass

from mocap_pose.domain.models import RawImuSample

from .cobs import cobs_decode
from .constants import (
    CRC_SIZE,
    HEADER_SIZE,
    MAGIC,
    MAX_ENCODED_FRAME_SIZE,
    PROTOCOL_VERSION,
    RAW_BATCH_ITEM_SIZE,
    RAW_SAMPLE_PAYLOAD_SIZE,
    MessageType,
)
from .crc import crc16_ccitt_false
from .errors import CrcMismatchError, FrameDecodeError, ProtocolError

HEADER = struct.Struct("<2sBBHBIQ")
RAW_SAMPLE = struct.Struct("<3h3h3hhHH")
BATCH_ITEM_HEADER = struct.Struct("<BIQ")


@dataclass(frozen=True, slots=True)
class Frame:
    message_type: MessageType
    node_id: int
    sequence: int
    timestamp_us: int
    payload: bytes
    version: int = PROTOCOL_VERSION


def decode_frame(encoded: bytes) -> Frame:
    decoded = cobs_decode(encoded.rstrip(b"\x00"))
    if len(decoded) < HEADER_SIZE + CRC_SIZE:
        raise FrameDecodeError("frame is shorter than header and CRC")
    body, crc_bytes = decoded[:-CRC_SIZE], decoded[-CRC_SIZE:]
    expected_crc = struct.unpack("<H", crc_bytes)[0]
    actual_crc = crc16_ccitt_false(body)
    if actual_crc != expected_crc:
        raise CrcMismatchError(
            f"CRC mismatch: received {expected_crc:04x}, calculated {actual_crc:04x}"
        )
    header_values = HEADER.unpack_from(body)
    magic, version, raw_type, payload_len, node_id, sequence, timestamp_us = header_values
    if magic != MAGIC:
        raise FrameDecodeError(f"unexpected magic {magic!r}")
    if version != PROTOCOL_VERSION:
        raise FrameDecodeError(f"unsupported protocol version {version}")
    if payload_len != len(body) - HEADER_SIZE:
        raise FrameDecodeError("payload length does not match frame length")
    try:
        message_type = MessageType(raw_type)
    except ValueError as exc:
        raise FrameDecodeError(f"unknown message type {raw_type}") from exc
    return Frame(message_type, node_id, sequence, timestamp_us, body[HEADER_SIZE:], version)


def decode_raw_sample(frame: Frame) -> RawImuSample:
    if frame.message_type is not MessageType.RAW_SAMPLE:
        raise FrameDecodeError("frame is not RAW_SAMPLE")
    if len(frame.payload) != RAW_SAMPLE_PAYLOAD_SIZE:
        raise FrameDecodeError("RAW_SAMPLE payload must be 24 bytes")
    return _raw_sample_from_payload(
        frame.node_id, frame.sequence, frame.timestamp_us, frame.payload
    )


def _raw_sample_from_payload(
    node_id: int, sequence: int, timestamp_us: int, payload: bytes
) -> RawImuSample:
    if len(payload) != RAW_SAMPLE_PAYLOAD_SIZE:
        raise FrameDecodeError("RAW_SAMPLE payload must be 24 bytes")
    values = RAW_SAMPLE.unpack(payload)
    return RawImuSample(
        node_id=node_id,
        sequence=sequence,
        device_timestamp_us=timestamp_us,
        accel_mg=values[0:3],
        gyro_dps_x10=values[3:6],
        mag_ut_x10=values[6:9],
        temperature_c_x100=values[9],
        mag_age_us=values[10],
        status_flags=values[11],
    )


def decode_raw_batch(frame: Frame) -> list[RawImuSample]:
    if frame.message_type is not MessageType.RAW_BATCH:
        raise FrameDecodeError("frame is not RAW_BATCH")
    if not frame.payload:
        raise FrameDecodeError("RAW_BATCH payload is missing count")
    count = frame.payload[0]
    if count == 0:
        raise FrameDecodeError("RAW_BATCH count must be non-zero")
    expected_length = 1 + count * RAW_BATCH_ITEM_SIZE
    if len(frame.payload) != expected_length:
        raise FrameDecodeError(
            f"RAW_BATCH count {count} requires {expected_length} bytes, got {len(frame.payload)}"
        )
    samples: list[RawImuSample] = []
    offset = 1
    for _ in range(count):
        node_id, sequence, timestamp_us = BATCH_ITEM_HEADER.unpack_from(frame.payload, offset)
        offset += BATCH_ITEM_HEADER.size
        payload = frame.payload[offset : offset + RAW_SAMPLE_PAYLOAD_SIZE]
        offset += RAW_SAMPLE_PAYLOAD_SIZE
        samples.append(_raw_sample_from_payload(node_id, sequence, timestamp_us, payload))
    return samples


class StreamDecoder:
    """Incrementally decodes a noisy byte stream using the zero frame delimiter."""

    def __init__(self, max_frame_size: int = MAX_ENCODED_FRAME_SIZE) -> None:
        self._buffer = bytearray()
        self._max_frame_size = max_frame_size
        self.frames_ok = 0
        self.frames_rejected = 0
        self.bytes_discarded = 0
        self.last_error: ProtocolError | None = None

    def feed(self, data: bytes) -> list[Frame]:
        frames: list[Frame] = []
        for byte in data:
            if byte == 0:
                if not self._buffer:
                    continue
                try:
                    frames.append(decode_frame(bytes(self._buffer)))
                    self.frames_ok += 1
                except ProtocolError as exc:
                    self.frames_rejected += 1
                    self.last_error = exc
                self._buffer.clear()
            elif len(self._buffer) >= self._max_frame_size:
                self.bytes_discarded += len(self._buffer) + 1
                self.frames_rejected += 1
                self._buffer.clear()
            else:
                self._buffer.append(byte)
        return frames
