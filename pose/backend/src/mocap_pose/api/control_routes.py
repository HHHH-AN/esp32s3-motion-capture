from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from mocap_pose.sources.replay_source import ReplaySource

router = APIRouter(prefix="/api", tags=["control"])


class SpeedRequest(BaseModel):
    speed: float = Field(gt=0, le=16)


@router.post("/calibration/mounting")
async def request_mounting_calibration(request: Request) -> Response:
    raise HTTPException(
        501,
        "live mounting capture is not enabled; use mocap-calibrate-mounting "
        "with a T-pose recording",
    )


@router.post("/record/start", status_code=204)
async def start_recording(request: Request) -> Response:
    controller = request.app.state.recording_controller
    if controller.active:
        raise HTTPException(409, "recording is already active")
    controller.start()
    return Response(status_code=204)


@router.post("/record/stop", status_code=204)
async def stop_recording(request: Request) -> Response:
    controller = request.app.state.recording_controller
    if not controller.active:
        raise HTTPException(409, "recording is not active")
    controller.stop()
    return Response(status_code=204)


@router.post("/playback/pause", status_code=204)
async def pause_playback(request: Request) -> Response:
    source = request.app.state.runtime.source
    if not isinstance(source, ReplaySource):
        raise HTTPException(409, "active source is not replay")
    source.pause()
    return Response(status_code=204)


@router.post("/playback/resume", status_code=204)
async def resume_playback(request: Request) -> Response:
    source = request.app.state.runtime.source
    if not isinstance(source, ReplaySource):
        raise HTTPException(409, "active source is not replay")
    source.resume()
    return Response(status_code=204)


@router.post("/playback/speed", status_code=204)
async def set_playback_speed(body: SpeedRequest, request: Request) -> Response:
    source = request.app.state.runtime.source
    if not isinstance(source, ReplaySource):
        raise HTTPException(409, "active source is not replay")
    source.set_speed(body.speed)
    return Response(status_code=204)
