from collections.abc import AsyncIterator

import pytest

from mocap_pose.domain.models import IngressPacket, RawImuSample
from mocap_pose.pipeline.runtime import MotionCaptureRuntime
from mocap_pose.protocol.encoder import encode_raw_batch
from mocap_pose.sources.base import PacketSource


class OnePacketSource(PacketSource):
    def __init__(self, data: bytes) -> None:
        self.data = data

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def packets(self) -> AsyncIterator[IngressPacket]:
        yield IngressPacket(self.data, 2_000_000, "test")


@pytest.mark.asyncio
async def test_runtime_expands_raw_batch_into_node_poses() -> None:
    samples = [
        RawImuSample(node, 1, 1_000_000, (0, 0, 1000), (0, 0, 0), (450, 0, 100), 2500, 0, 0xF)
        for node in (1, 2)
    ]
    poses = []
    runtime = MotionCaptureRuntime(
        OnePacketSource(encode_raw_batch(samples, 7, 1_000_000)),
        expected_nodes=(1, 2),
        on_pose=lambda pose: _append(poses, pose),
    )
    await runtime.run()
    assert [pose.node_id for pose in poses] == [1, 2]


async def _append(values, value) -> None:
    values.append(value)

