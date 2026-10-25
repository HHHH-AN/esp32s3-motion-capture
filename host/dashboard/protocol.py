from __future__ import annotations

import math
import re

from .models import SensorSample


class FrameError(ValueError):
    pass


class CurrentCsvProtocol:
    """Accept legacy CSV and IMU2,id,sequence,micros,flags,<11 values>."""

    column_count = 11

    def parse(self, line: str) -> SensorSample | None:
        stripped = line.strip()
        if not stripped or stripped.startswith(("=", "AccX", "数据格式", "[")):
            return None
        parts = stripped.split(",")
        node_id, sequence, device_us, flags = "right_wrist", None, None, 3
        if parts[0] == "IMU2":
            if len(parts) != 16:
                raise FrameError("IMU2 requires 16 columns")
            _, node_id, seq_text, time_text, flag_text, *parts = parts
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", node_id):
                raise FrameError("invalid node ID")
            try:
                sequence, device_us, flags = int(seq_text), int(time_text), int(flag_text)
            except ValueError as exc:
                raise FrameError("invalid frame metadata") from exc
            if not (0 <= sequence < 2**32 and 0 <= device_us < 2**32 and 0 <= flags <= 3):
                raise FrameError("frame metadata out of range")
        if len(parts) != self.column_count:
            raise FrameError(f"expected 11 columns, received {len(parts)}")
        try:
            values = tuple(float(value) for value in parts)
        except ValueError as exc:
            raise FrameError("frame contains a non-numeric value") from exc
        if not all(math.isfinite(value) for value in values):
            raise FrameError("frame contains a non-finite value")
        ax, ay, az, gx, gy, gz, temp, mx, my, mz, mag_temp = values
        if max(abs(gx), abs(gy), abs(gz)) > 4000:
            raise FrameError("gyroscope value outside safety range")
        if max(abs(ax), abs(ay), abs(az)) > 200:
            raise FrameError("accelerometer value outside safety range")
        return SensorSample((ax, ay, az), (gx, gy, gz), (mx, my, mz), temp, mag_temp,
                            node_id=node_id, sequence=sequence, device_us=device_us, sensor_flags=flags)

