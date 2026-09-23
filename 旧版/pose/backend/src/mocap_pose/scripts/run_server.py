import argparse
from pathlib import Path

import uvicorn

from mocap_pose.api.app import create_app
from mocap_pose.config.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the motion-capture local bridge")
    parser.add_argument("--source", choices=("mock", "serial", "ble", "replay"), default="mock")
    parser.add_argument("--port", dest="serial_port")
    parser.add_argument("--address", dest="ble_address")
    parser.add_argument("--path", type=Path, dest="replay_path")
    parser.add_argument("--speed", type=float, default=1.0, dest="replay_speed")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8000)
    args = parser.parse_args()
    settings = Settings(
        source=args.source,
        serial_port=args.serial_port,
        ble_address=args.ble_address,
        replay_path=args.replay_path,
        replay_speed=args.replay_speed,
    )
    uvicorn.run(create_app(settings), host=args.host, port=args.http_port)


if __name__ == "__main__":
    main()

