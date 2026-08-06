from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any


class Broadcaster:
    def __init__(self, subscriber_capacity: int = 4) -> None:
        self.subscriber_capacity = subscriber_capacity
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    async def publish(self, message: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)

    @asynccontextmanager
    async def subscribe(self):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self.subscriber_capacity)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

