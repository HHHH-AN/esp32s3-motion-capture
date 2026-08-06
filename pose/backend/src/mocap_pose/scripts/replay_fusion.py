import argparse
import asyncio
from pathlib import Path

from mocap_pose.pipeline.runtime import MotionCaptureRuntime
from mocap_pose.sources.replay_source import ReplaySource


async def replay(path: Path, speed: float) -> None:
    async def print_pose(pose) -> None:
        print(pose.to_message())

    await MotionCaptureRuntime(ReplaySource(path, speed), on_pose=print_pose).run()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a session through the production fusion pipeline"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    asyncio.run(replay(args.path, args.speed))


if __name__ == "__main__":
    main()
