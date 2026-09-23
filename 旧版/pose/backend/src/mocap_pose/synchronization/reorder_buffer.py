from __future__ import annotations

import heapq
from collections.abc import Iterable
from typing import Generic, TypeVar

T = TypeVar("T")


class ReorderBuffer(Generic[T]):
    def __init__(self, window_us: int = 30_000) -> None:
        self.window_us = window_us
        self._heap: list[tuple[int, int, T]] = []
        self._latest_us = -1
        self._counter = 0

    def push(self, timestamp_us: int, item: T) -> list[T]:
        self._latest_us = max(self._latest_us, timestamp_us)
        heapq.heappush(self._heap, (timestamp_us, self._counter, item))
        self._counter += 1
        return self._release_before(self._latest_us - self.window_us)

    def _release_before(self, watermark_us: int) -> list[T]:
        output: list[T] = []
        while self._heap and self._heap[0][0] <= watermark_us:
            output.append(heapq.heappop(self._heap)[2])
        return output

    def flush(self) -> list[T]:
        output = [heapq.heappop(self._heap)[2] for _ in range(len(self._heap))]
        return output

    def extend(self, values: Iterable[tuple[int, T]]) -> list[T]:
        output: list[T] = []
        for timestamp, value in values:
            output.extend(self.push(timestamp, value))
        return output

