from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .service import Runtime
from .recordings import RecordingNotFound, catalog, preview_csv, safe_item, session_zip


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web"
app = FastAPI(title="14 节点 IMU 运动可视化")
runtime = Runtime()
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
async def status():
    return runtime.payload()


@app.get("/api/recordings")
async def recordings():
    return {"items": catalog(), "active": runtime.record_path if runtime.recording else None}


@app.get("/api/recordings/{session}/preview")
async def recording_preview(session: str, file: str, limit: int = 100):
    try:
        return preview_csv(session, file, limit)
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
        content = session_zip(session)
        return Response(content, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{session}.zip"'})
    except RecordingNotFound:
        raise HTTPException(status_code=404, detail="记录会话不存在")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    runtime.clients.add(websocket)
    await websocket.send_json(runtime.payload())
    try:
        while True:
            await runtime.command(await websocket.receive_json())
    except WebSocketDisconnect:
        runtime.clients.discard(websocket)
