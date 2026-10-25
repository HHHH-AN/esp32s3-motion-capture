"""Print ESP32 CSV frames over Wi-Fi; only Python's standard library is needed."""

import argparse
import socket
import sys

from dashboard.protocol import CurrentCsvProtocol, FrameError


def receive(host: str, port: int, count: int = 0) -> None:
    protocol = CurrentCsvProtocol()
    with socket.create_connection((host, port), timeout=5) as connection:
        connection.settimeout(3)
        with connection.makefile("rb") as stream:
            print(f"Connected to {host}:{port}", file=sys.stderr)
            received = 0
            while not count or received < count:
                raw = stream.readline(4097)
                if not raw:
                    raise ConnectionError("ESP32 closed the connection")
                if len(raw) > 4096 or not raw.endswith(b"\n"):
                    raise ConnectionError("Incomplete or overlong CSV frame")
                try:
                    line = raw.decode("utf-8").strip()
                    sample = protocol.parse(line)
                    if sample is None:
                        continue
                except (FrameError, UnicodeDecodeError) as error:
                    print(f"Invalid frame: {error}", file=sys.stderr)
                    continue
                if received == 0:
                    header = "AccX(g),AccY(g),AccZ(g),GyrX(dps),GyrY(dps),GyrZ(dps),ICMTemp(C),MagX(mG),MagY(mG),MagZ(mG),LISTemp(raw)"
                    if sample.sequence is not None:
                        header = "Protocol,NodeID,Sequence,DeviceMicros,SensorFlags," + header
                    print(header, flush=True)
                print(line, flush=True)
                received += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="ESP32 IP printed in the USB serial log")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--count", type=int, default=0, help="Stop after N frames; 0 means continuous")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.count < 0:
        parser.error("port must be 1..65535 and count must be nonnegative")
    try:
        receive(args.host, args.port, args.count)
    except KeyboardInterrupt:
        return 0
    except (OSError, ConnectionError) as error:
        print(f"Receive failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
