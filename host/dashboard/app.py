from pathlib import Path
import asyncio
import json
from contextlib import asynccontextmanager
from serial.tools import list_ports

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

from .service import Runtime
from .recordings import RecordingNotFound, catalog, preview_csv, safe_item, session_zip, replay_data


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web"
runtime = Runtime()


@asynccontextmanager
async def lifespan(app):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.close()


app = FastAPI(title="IMU 单节点开发台", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
async def status():
    return runtime.payload()


@app.get("/api/recordings")
async def recordings():
    return {"items": await asyncio.to_thread(catalog), "active": runtime.record_path if runtime.recording else None}


@app.get("/api/ports")
async def ports():
    devices = await asyncio.to_thread(list_ports.comports)
    return {"items": [{"device": p.device, "description": p.description} for p in devices]}


@app.get("/api/recordings/{session}/replay")
async def recording_replay(session: str):
    if runtime.recording and Path(runtime.record_path).name == session:
        raise HTTPException(status_code=409, detail="请先停止记录再回放")
    try:
        return await asyncio.to_thread(replay_data, session)
    except RecordingNotFound:
        raise HTTPException(status_code=404, detail="记录不存在")


@app.get("/api/recordings/{session}/preview")
async def recording_preview(session: str, file: str, limit: int = 100):
    try:
        return await asyncio.to_thread(preview_csv, session, file, limit)
    except RecordingNotFound:
        raise HTTPException(status_code=404, detail="记录文件不存在")


@app.get("/api/recordings/{session}/download")
async def recording_download(session: str):
    active_name = Path(runtime.record_path).name if runtime.recording and runtime.record_path else None
    if session == active_name:
        raise HTTPException(status_code=409, detail="请先停止记录再导出")
    try:
        item = safe_item(session)
        if item.is_file() and item.suffix.lower() == ".jsonl":
            return FileResponse(item, filename=item.name, media_type="application/x-ndjson")
        content = await asyncio.to_thread(session_zip, session)
        return Response(content, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{session}.zip"'})
    except RecordingNotFound:
        raise HTTPException(status_code=404, detail="记录会话不存在")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json(runtime.payload())
    runtime.clients.add(websocket)
    try:
        while websocket.application_state == WebSocketState.CONNECTED:
            try:
                await runtime.command(await websocket.receive_json())
            except (json.JSONDecodeError, ValueError):
                runtime.message = "无法解析命令 JSON"
    except WebSocketDisconnect:
        pass
    finally:
        runtime.clients.discard(websocket)
