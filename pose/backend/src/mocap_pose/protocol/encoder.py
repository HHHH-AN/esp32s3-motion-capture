import struct

from mocap_pose.domain.models import RawImuSample

from .cobs import cobs_encode
from .constants import MAGIC, MessageType
from .crc import crc16_ccitt_false
from .decoder import BATCH_ITEM_HEADER, HEADER, RAW_SAMPLE, Frame


def encode_frame(frame: Frame) -> bytes:
    if not 0 <= frame.node_id <= 0xFF:
        raise ValueError("node_id must fit uint8")
    if not 0 <= frame.sequence <= 0xFFFFFFFF:
        raise ValueError("sequence must fit uint32")
    if len(frame.payload) > 0xFFFF:
        raise ValueError("payload is too long")
    header = HEADER.pack(
        MAGIC,
        frame.version,
        int(frame.message_type),
        len(frame.payload),
        frame.node_id,
        frame.sequence,
        frame.timestamp_us,
    )
    body = header + frame.payload
    return cobs_encode(body + struct.pack("<H", crc16_ccitt_false(body))) + b"\x00"


def encode_raw_sample(sample: RawImuSample) -> bytes:
    payload = _encode_raw_payload(sample)
    return encode_frame(
        Frame(
            MessageType.RAW_SAMPLE,
            sample.node_id,
            sample.sequence,
            sample.device_timestamp_us,
            payload,
        )
    )


def _encode_raw_payload(sample: RawImuSample) -> bytes:
    return RAW_SAMPLE.pack(
        *sample.accel_mg,
        *sample.gyro_dps_x10,
        *sample.mag_ut_x10,
        sample.temperature_c_x100,
        sample.mag_age_us,
        sample.status_flags,
    )


def encode_raw_batch(
    samples: list[RawImuSample], sequence: int, timestamp_us: int
) -> bytes:
    if not samples or len(samples) > 255:
        raise ValueError("RAW_BATCH requires between 1 and 255 samples")
    payload = bytearray((len(samples),))
    for sample in samples:
        payload.extend(
            BATCH_ITEM_HEADER.pack(sample.node_id, sample.sequence, sample.device_timestamp_us)
        )
        payload.extend(_encode_raw_payload(sample))
    return encode_frame(
        Frame(
            MessageType.RAW_BATCH,
            0,
            sequence,
            timestamp_us,
            bytes(payload),
        )
    )
