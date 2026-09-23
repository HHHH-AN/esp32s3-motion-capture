from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    source: str = "mock"
    serial_port: str | None = None
    serial_baudrate: int = 921_600
    replay_path: Path | None = None
    replay_speed: float = 1.0
    ble_address: str | None = None
    ble_name_prefix: str = "MOCAP-"
    ble_data_characteristic: str = "a0e50002-7c2b-4f18-a902-6f34bca10001"
    ble_status_characteristic: str = "a0e50003-7c2b-4f18-a902-6f34bca10001"
    ble_control_characteristic: str = "a0e50004-7c2b-4f18-a902-6f34bca10001"
    queue_capacity: int = 2048
    reconnect_delay_s: float = 2.0
    expected_nodes: tuple[int, ...] = tuple(range(1, 15))
    frame_rate_hz: int = 60
