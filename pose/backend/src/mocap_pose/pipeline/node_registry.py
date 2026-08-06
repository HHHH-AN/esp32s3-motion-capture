from __future__ import annotations

from mocap_pose.domain.models import DeviceState


class NodeRegistry:
    def __init__(self, offline_after_us: int = 500_000) -> None:
        self.offline_after_us = offline_after_us
        self.nodes: dict[int, DeviceState] = {}

    def observe(self, node_id: int, sequence: int, now_us: int) -> DeviceState:
        state = self.nodes.setdefault(node_id, DeviceState(node_id))
        previous = state.errors.get("last_sequence")
        if previous is not None:
            state.packets_lost += max(0, ((sequence - previous) & 0xFFFFFFFF) - 1)
        state.errors["last_sequence"] = sequence
        state.last_seen_us = now_us
        state.packets_received += 1
        state.online = True
        return state

    def refresh(self, now_us: int) -> None:
        for state in self.nodes.values():
            state.online = now_us - state.last_seen_us <= self.offline_after_us
