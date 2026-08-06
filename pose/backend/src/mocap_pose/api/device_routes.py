from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from mocap_pose.sources.ble_source import BleSource
from mocap_pose.sources.mock_source import MockSource

router = APIRouter(prefix="/api/devices", tags=["devices"])


class ConnectRequest(BaseModel):
    id: str


@router.get("")
async def list_devices(request: Request) -> dict[str, object]:
    runtime = request.app.state.runtime
    return {
        "source": type(runtime.source).__name__,
        "nodes": [
            {
                "node_id": node_id,
                "clock_ready": clock.ready,
                "clock_rms_error_us": clock.rms_error_us,
            }
            for node_id, clock in sorted(runtime.clock_models.items())
        ],
    }


@router.post("/scan")
async def scan_devices(request: Request) -> list[dict[str, object]]:
    source = request.app.state.runtime.source
    if isinstance(source, MockSource):
        return [{"id": "mock-bridge", "name": "MOCAP Mock Bridge", "connected": True}]
    if not isinstance(source, BleSource):
        raise HTTPException(409, "active source is not BLE")
    try:
        from bleak import BleakScanner

        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
    except Exception as exc:
        raise HTTPException(503, f"BLE scan failed: {exc}") from exc
    result: list[dict[str, object]] = []
    for address, (device, advertisement) in devices.items():
        name = device.name or advertisement.local_name or ""
        if name.startswith(source.name_prefix):
            result.append(
                {
                    "id": address,
                    "name": name,
                    "rssi": advertisement.rssi,
                    "connected": bool(source._client and source._client.is_connected),
                }
            )
    return result


@router.post("/connect", status_code=204)
async def connect_device(body: ConnectRequest, request: Request) -> Response:
    source = request.app.state.runtime.source
    if isinstance(source, MockSource) and body.id == "mock-bridge":
        return Response(status_code=204)
    if not isinstance(source, BleSource):
        raise HTTPException(409, "active source is not BLE")
    await source.connect(body.id)
    return Response(status_code=204)


@router.post("/disconnect", status_code=204)
async def disconnect_device(request: Request) -> Response:
    source = request.app.state.runtime.source
    if isinstance(source, BleSource):
        await source.disconnect()
    elif not isinstance(source, MockSource):
        raise HTTPException(409, "active source does not support disconnect")
    return Response(status_code=204)
