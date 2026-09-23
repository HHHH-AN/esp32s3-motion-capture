from __future__ import annotations

from collections import deque


class ClockModel:
    """Online affine mapping from device microseconds to host monotonic microseconds."""

    def __init__(self, window_size: int = 120) -> None:
        if window_size < 2:
            raise ValueError("window_size must be at least two")
        self._samples: deque[tuple[int, int]] = deque(maxlen=window_size)
        self.slope = 1.0
        self.intercept = 0.0
        self.rms_error_us = float("inf")

    def update(self, device_time_us: int, host_time_us: int) -> None:
        if self._samples and device_time_us <= self._samples[-1][0]:
            self._samples.clear()
        self._samples.append((device_time_us, host_time_us))
        if len(self._samples) == 1:
            self.intercept = host_time_us - device_time_us
            return
        mean_x = sum(sample[0] for sample in self._samples) / len(self._samples)
        mean_y = sum(sample[1] for sample in self._samples) / len(self._samples)
        denominator = sum((x - mean_x) ** 2 for x, _ in self._samples)
        if denominator <= 0:
            return
        self.slope = sum((x - mean_x) * (y - mean_y) for x, y in self._samples) / denominator
        self.intercept = mean_y - self.slope * mean_x
        residuals = [y - self.to_host_time(x) for x, y in self._samples]
        self.rms_error_us = (sum(value * value for value in residuals) / len(residuals)) ** 0.5

    def to_host_time(self, device_time_us: int) -> int:
        return round(self.slope * device_time_us + self.intercept)

    @property
    def ready(self) -> bool:
        return len(self._samples) >= 2

