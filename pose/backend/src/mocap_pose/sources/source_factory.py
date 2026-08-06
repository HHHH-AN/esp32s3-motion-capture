from mocap_pose.config.settings import Settings

from .base import PacketSource
from .ble_source import BleSource
from .mock_source import MockSource
from .replay_source import ReplaySource
from .serial_source import SerialSource


def create_source(settings: Settings) -> PacketSource:
    match settings.source:
        case "mock":
            return MockSource()
        case "serial":
            if not settings.serial_port:
                raise ValueError("serial source requires serial_port")
            return SerialSource(settings.serial_port, settings.serial_baudrate)
        case "replay":
            if settings.replay_path is None:
                raise ValueError("replay source requires replay_path")
            return ReplaySource(settings.replay_path, settings.replay_speed)
        case "ble":
            return BleSource(
                settings.ble_data_characteristic,
                settings.ble_address,
                settings.ble_name_prefix,
                settings.queue_capacity,
                settings.reconnect_delay_s,
            )
        case _:
            raise ValueError(f"unknown source {settings.source!r}")

