"""Versioned device processing profiles; never infer identity from IP or body slot."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

DEFAULT_ATTITUDE_CONFIG = Path(__file__).resolve().parents[1]/"config/attitude_v1.json"


def load_attitude_config(path=None):
    return validate_attitude_config(json.loads(Path(path or DEFAULT_ATTITUDE_CONFIG).read_text(encoding="utf-8")))


def validate_attitude_config(value):
    result = deepcopy(value)
    if result.get("schema_version") != "attitude-processing/1":
        raise ValueError("不支持的姿态处理配置版本")
    profiles = result.get("profiles", {})
    if not isinstance(profiles, dict) or result.get("default_profile") not in profiles:
        raise ValueError("缺少有效的默认融合配置")
    for name, settings in profiles.items():
        if not isinstance(name,str) or not isinstance(settings,dict) or settings.get("mode") not in ("six_axis_relative","magnetic_guarded"):
            raise ValueError("无效融合配置")
        for key in ("gravity_vector_correction","stability_enabled"):
            if type(settings.get(key)) is not bool:
                raise ValueError("融合/停稳开关必须为布尔值")
    devices = result.get("device_profiles", {})
    if not isinstance(devices,dict) or any(not isinstance(key,str) or profile not in profiles for key, profile in devices.items()):
        raise ValueError("设备融合配置引用不存在")
    result.pop("config_version",None)
    encoded = json.dumps(result,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()
    result["config_version"] = "attitude-v1-"+hashlib.sha256(encoded).hexdigest()[:16]
    return result


def device_profile(config, device_id, profile=None):
    name = profile or config.get("device_profiles",{}).get(device_id,config["default_profile"])
    if name not in config["profiles"]:
        raise ValueError("未知姿态处理配置")
    return name, deepcopy(config["profiles"][name])
