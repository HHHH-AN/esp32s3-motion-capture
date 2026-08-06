from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from mocap_pose.calibration.apply import apply_calibration
from mocap_pose.calibration.schema import SensorCalibration
from mocap_pose.domain.models import IngressPacket, NodePose, SkeletonFrame
from mocap_pose.fusion.service import FusionService
from mocap_pose.protocol.constants import MessageType
from mocap_pose.protocol.decoder import StreamDecoder, decode_raw_batch, decode_raw_sample
from mocap_pose.quality.runtime_metrics import RuntimeMetrics
from mocap_pose.skeleton.kinematics import SkeletonKinematics
from mocap_pose.skeleton.layout import load_default_profile
from mocap_pose.sources.base import PacketSource
from mocap_pose.synchronization.clock_model import ClockModel
from mocap_pose.synchronization.frame_builder import FrameBuilder
from mocap_pose.synchronization.reorder_buffer import ReorderBuffer

PoseCallback = Callable[[NodePose], Awaitable[None]]
SkeletonCallback = Callable[[SkeletonFrame], Awaitable[None]]
PacketObserver = Callable[[IngressPacket], None]


async def _ignore_pose(_pose: NodePose) -> None:
    return None


async def _ignore_skeleton(_frame: SkeletonFrame) -> None:
    return None


class MotionCaptureRuntime:
    """Single acquisition pipeline shared by mock, replay, USB and BLE sources."""

    def __init__(
        self,
        source: PacketSource,
        expected_nodes: tuple[int, ...] = tuple(range(1, 15)),
        frame_rate_hz: int = 60,
        on_pose: PoseCallback = _ignore_pose,
        on_skeleton: SkeletonCallback = _ignore_skeleton,
        calibrations: dict[int, SensorCalibration] | None = None,
    ) -> None:
        self.source = source
        self.decoder = StreamDecoder()
        self.metrics = RuntimeMetrics()
        self.fusion = FusionService()
        self.clock_models: dict[int, ClockModel] = {}
        self.frame_builder = FrameBuilder(expected_nodes)
        self.reorder_buffer: ReorderBuffer[NodePose] = ReorderBuffer(window_us=30_000)
        self.kinematics = SkeletonKinematics(load_default_profile())
        self.frame_interval_us = round(1_000_000 / frame_rate_hz)
        self.on_pose = on_pose
        self.on_skeleton = on_skeleton
        self.calibrations = calibrations or {}
        self.packet_observers: list[PacketObserver] = []
        self._running = False

    async def run(self) -> None:
        self._running = True
        await self.source.start()
        ticker = asyncio.create_task(self._skeleton_ticker(), name="skeleton-ticker")
        try:
            async for packet in self.source.packets():
                if not self._running:
                    break
                for observer in tuple(self.packet_observers):
                    observer(packet)
                self.metrics.on_packet(len(packet.data))
                frames = self.decoder.feed(packet.data)
                self.metrics.rejected_frames = self.decoder.frames_rejected
                for frame in frames:
                    self.metrics.on_frame(frame.node_id, frame.sequence)
                    if frame.message_type is MessageType.RAW_SAMPLE:
                        samples = [decode_raw_sample(frame)]
                    elif frame.message_type is MessageType.RAW_BATCH:
                        samples = decode_raw_batch(frame)
                    else:
                        continue
                    for raw in samples:
                        if frame.message_type is MessageType.RAW_BATCH:
                            self.metrics.on_frame(raw.node_id, raw.sequence)
                        calibrated = apply_calibration(raw, self.calibrations.get(raw.node_id))
                        clock = self.clock_models.setdefault(raw.node_id, ClockModel())
                        clock.update(raw.device_timestamp_us, packet.arrival_time_us)
                        host_time_us = clock.to_host_time(raw.device_timestamp_us)
                        pose = self.fusion.update(calibrated, host_time_us)
                        pose = NodePose(
                            pose.node_id,
                            pose.frame_time_us,
                            pose.quaternion_wxyz,
                            pose.quality,
                            max(0.0, (packet.arrival_time_us - host_time_us) / 1000),
                            pose.status_flags,
                        )
                        for released in self.reorder_buffer.push(pose.frame_time_us, pose):
                            await self._publish_pose(released)
        finally:
            for pose in self.reorder_buffer.flush():
                await self._publish_pose(pose)
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)
            await self.source.stop()
            self._running = False

    async def _publish_pose(self, pose: NodePose) -> None:
        self.frame_builder.add(pose)
        await self.on_pose(pose)

    async def _skeleton_ticker(self) -> None:
        interval_s = self.frame_interval_us / 1_000_000
        while self._running:
            now_us = round(asyncio.get_running_loop().time() * 1_000_000)
            synchronized = self.frame_builder.build(now_us)
            await self.on_skeleton(self.kinematics.solve(synchronized))
            await asyncio.sleep(interval_s)

    async def stop(self) -> None:
        self._running = False
        await self.source.stop()
        await asyncio.sleep(0)
