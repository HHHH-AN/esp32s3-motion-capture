import argparse
import os
from pathlib import Path

import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local IMU dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--body-config", type=Path, help="Versioned body layout JSON; defaults to host/config/body_v1.json")
    args = parser.parse_args()
    if args.body_config:
        if not args.body_config.is_file():
            parser.error("--body-config must be an existing JSON file")
        os.environ["IMU_BODY_CONFIG"] = str(args.body_config.resolve())
    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=False)

