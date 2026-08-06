import argparse
import asyncio
import datetime as dt
from pathlib import Path

from mocap_pose.config.settings import Settings
from mocap_pose.sources.source_factory import create_source
from mocap_pose.storage.raw_session import RawSessionWriter


async def record(settings: Settings, root: Path, duration_s: float) -> Path:
    source = create_source(settings)
    name = dt.datetime.now().strftime("session_%Y%m%d_%H%M%S")
    path = root / name
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration_s
    await source.start()
    try:
        with RawSessionWriter(
            path,
            {
                "protocol_version": 1,
                "firmware_version": "reported-per-device-or-unknown",
                "config_version": "human-14-v1",
                "nodes": list(settings.expected_nodes),
                "source": settings.source,
                "created_at": dt.datetime.now().isoformat(),
            },
        ) as writer:
            async for packet in source.packets():
                writer.write(packet)
                if loop.time() >= deadline:
                    break
    finally:
        await source.stop()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Record transport bytes for deterministic replay")
    parser.add_argument("--source", choices=("mock", "serial", "ble"), default="serial")
    parser.add_argument("--port", dest="serial_port")
    parser.add_argument("--address", dest="ble_address")
    parser.add_argument("--output", type=Path, default=Path("recordings"))
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()
    path = asyncio.run(
        record(
            Settings(
                source=args.source,
                serial_port=args.serial_port,
                ble_address=args.ble_address,
            ),
            args.output,
            args.duration,
        )
    )
    print(path)


if __name__ == "__main__":
    main()
