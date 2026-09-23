from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from mocap_pose.config.settings import Settings
from mocap_pose.domain.models import NodePose
from mocap_pose.pipeline.runtime import MotionCaptureRuntime
from mocap_pose.sources.base import PacketSource
from mocap_pose.sources.source_factory import create_source

from .broadcaster import Broadcaster
from .control_routes import router as control_router
from .device_routes import router as device_router
from .latest_pose import LatestPoseStore
from .recording_controller import RecordingController
from .recording_routes import router as recording_router


def create_app(settings: Settings | None = None, source: PacketSource | None = None) -> FastAPI:
    settings = settings or Settings()
    latest_poses = LatestPoseStore()
    skeleton_messages = Broadcaster()

    async def retain_latest_pose(pose: NodePose) -> None:
        latest_poses.update(pose)

    runtime = MotionCaptureRuntime(
        source or create_source(settings),
        settings.expected_nodes,
        settings.frame_rate_hz,
        retain_latest_pose,
        lambda frame: skeleton_messages.publish(frame.to_message()),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        task = asyncio.create_task(runtime.run(), name="motion-capture-runtime")
        application.state.runtime_task = task
        try:
            yield
        finally:
            if recording_controller.active:
                recording_controller.stop()
            await runtime.stop()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    application = FastAPI(title="Motion Capture Pose API", version="0.1.0", lifespan=lifespan)
    application.state.runtime = runtime
    application.state.latest_poses = latest_poses
    application.state.skeleton_messages = skeleton_messages
    recording_controller = RecordingController(Path("recordings"), settings.expected_nodes)
    application.state.recording_controller = recording_controller
    runtime.packet_observers.append(recording_controller.observe)
    application.include_router(control_router)
    application.include_router(device_router)
    application.include_router(recording_router)

    @application.get("/api/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "metrics": runtime.metrics.snapshot()}

    async def websocket_stream(websocket: WebSocket, broadcaster: Broadcaster) -> None:
        await websocket.accept()
        try:
            async with broadcaster.subscribe() as queue:
                while True:
                    await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            return

    @application.websocket("/ws/pose")
    async def pose_socket(websocket: WebSocket) -> None:
        raw_node_id = websocket.query_params.get("node_id", "1")
        try:
            node_id = int(raw_node_id)
        except ValueError:
            await websocket.close(code=1008, reason="node_id must be an integer")
            return
        if not 1 <= node_id <= 14:
            await websocket.close(code=1008, reason="node_id must be between 1 and 14")
            return
        await websocket.accept()
        last_frame_time_us = -1
        interval_s = 1 / settings.frame_rate_hz
        try:
            while True:
                pose = latest_poses.get(node_id)
                if pose is not None and pose.frame_time_us > last_frame_time_us:
                    await websocket.send_json(pose.to_message())
                    last_frame_time_us = pose.frame_time_us
                await asyncio.sleep(interval_s)
        except WebSocketDisconnect:
            return

    @application.websocket("/ws/skeleton")
    async def skeleton_socket(websocket: WebSocket) -> None:
        await websocket_stream(websocket, skeleton_messages)

    return application


app = create_app()
