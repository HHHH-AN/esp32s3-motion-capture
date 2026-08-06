import argparse
import asyncio

from mocap_pose.config.settings import Settings
from mocap_pose.protocol.constants import MessageType
from mocap_pose.protocol.decoder import StreamDecoder, decode_raw_batch, decode_raw_sample
from mocap_pose.sources.source_factory import create_source


async def inspect(settings: Settings, limit: int) -> None:
    source = create_source(settings)
    decoder = StreamDecoder()
    count = 0
    await source.start()
    try:
        async for packet in source.packets():
            for frame in decoder.feed(packet.data):
                if frame.message_type is MessageType.RAW_SAMPLE:
                    samples = [decode_raw_sample(frame)]
                elif frame.message_type is MessageType.RAW_BATCH:
                    samples = decode_raw_batch(frame)
                else:
                    continue
                for sample in samples:
                    print(
                        f"node={sample.node_id:02d} seq={sample.sequence:10d} "
                        f"a_mg={sample.accel_mg} g_x10={sample.gyro_dps_x10} "
                        f"m_uT_x10={sample.mag_ut_x10}"
                    )
                    count += 1
                    if count >= limit:
                        return
    finally:
        await source.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect decoded raw IMU samples")
    parser.add_argument("--source", choices=("mock", "serial", "ble", "replay"), default="mock")
    parser.add_argument("--port", dest="serial_port")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(inspect(Settings(source=args.source, serial_port=args.serial_port), args.limit))


if __name__ == "__main__":
    main()

