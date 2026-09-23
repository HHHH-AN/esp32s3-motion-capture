import argparse

import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local IMU dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=False)

