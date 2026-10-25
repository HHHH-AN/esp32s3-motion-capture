from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import monotonic, time
from typing import Literal


NODE_DEFINITIONS = (
    ("waist", "腰部"), ("head", "头部"),
    ("left_shoulder", "左肩"), ("left_elbow", "左肘"), ("left_wrist", "左腕"),
    ("right_shoulder", "右肩"), ("right_elbow", "右肘"), ("right_wrist", "右腕"),
    ("left_hip", "左髋"), ("left_knee", "左膝"), ("left_ankle", "左踝"),
    ("right_hip", "右髋"), ("right_knee", "右膝"), ("right_ankle", "右踝"),
)


@dataclass(slots=True)
class SensorSample:
    accel: tuple[float, float, float]
    gyro: tuple[float, float, float]
    mag: tuple[float, float, float]
    temperature: float
    aux_temperature: float
    received_monotonic: float = field(default_factory=monotonic)
    received_unix: float = field(default_factory=time)
    node_id: str = "right_wrist"
    sequence: int | None = None
    device_us: int | None = None
    sensor_flags: int = 3
    # Physical identity is node_id. A missing body_slot is deliberately unbound;
    # the legacy node_id spelling must never imply an installation role.
    body_slot: str | None = None
    boot_id: str | None = None
    firmware_version: str | None = None
    config_version: str | None = None
    protocol_version: str = "legacy"


@dataclass(slots=True)
class NodeState:
    id: str
    name: str
    source: Literal["real", "static_simulated"]
    quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    accel: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gyro: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mag: tuple[float, float, float] = (0.0, 0.0, 0.0)
    temperature: float = 0.0
    aux_temperature: float = 0.0
    valid: bool = True
    updated_at: float | None = None

    def payload(self) -> dict:
        return asdict(self)


def initial_nodes() -> dict[str, NodeState]:
    nodes = {
        node_id: NodeState(node_id, name, "static_simulated")
        for node_id, name in NODE_DEFINITIONS
    }
    nodes["right_wrist"].source = "real"
    nodes["right_wrist"].valid = False
    return nodes
