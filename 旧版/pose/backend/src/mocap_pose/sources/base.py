from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from mocap_pose.domain.models import IngressPacket


class PacketSource(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def packets(self) -> AsyncIterator[IngressPacket]: ...

