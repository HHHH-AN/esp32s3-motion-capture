from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


@router.get("")
async def list_recordings(root: str = "recordings") -> dict[str, object]:
    path = Path(root).resolve()
    if not path.exists():
        return {"recordings": []}
    if not path.is_dir():
        raise HTTPException(400, "recording root is not a directory")
    return {
        "recordings": [entry.name for entry in sorted(path.iterdir()) if entry.is_dir()]
    }

