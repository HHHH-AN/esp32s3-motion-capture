from __future__ import annotations

import math

from .models import SensorSample


class FrameError(ValueError):
    pass


class CurrentCsvProtocol:
    """Adapter for the current 11-column ESP32 CSV stream."""

    column_count = 11

    def parse(self, line: str) -> SensorSample | None:
        stripped = line.strip()
        if not stripped or stripped.startswith(("=", "AccX", "数据格式", "[")):
            return None
        parts = stripped.split(",")
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
        return SensorSample((ax, ay, az), (gx, gy, gz), (mx, my, mz), temp, mag_temp)

