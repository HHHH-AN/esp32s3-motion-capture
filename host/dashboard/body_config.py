"""Versioned layout is data, not a hard-coded promise about physical mounting."""
from copy import deepcopy
import json
import math
from pathlib import Path

from .coordinates import CoordinateSettings

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "body_v1.json"


def load_config(path=None):
    data = json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    return validate_config(data)


def validate_config(value):
    data = deepcopy(value)
    if data.get("schema_version") != "body-layout/1":
        raise ValueError("不支持的骨架配置版本")
    segments = data.get("segments", [])
    if not segments:
        raise ValueError("骨架至少需要一段")
    seen = set()
    for item in segments:
        node_id = item.get("id")
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            raise ValueError("骨段 ID 无效或重复")
        if item.get("parent") is not None and item["parent"] not in seen:
            raise ValueError("骨段需按父先子后排序，且不允许环")
        seen.add(node_id)
        length = item.get("length")
        if isinstance(length, bool) or not isinstance(length, (int, float)) or not math.isfinite(length) or not 0.01 <= length <= 3:
            raise ValueError("骨长必须在 0.01–3 米内")
        for key in ("anchor", "direction"):
            values = item.get(key)
            if not isinstance(values, list) or len(values) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                raise ValueError("无效骨架向量")
        norm = math.sqrt(sum(v*v for v in item["direction"]))
        if norm < 1e-9:
            raise ValueError("骨段方向不能为零")
        item["direction"] = [v/norm for v in item["direction"]]
    if sum(item.get("parent") is None for item in segments) != 1:
        raise ValueError("骨架必须只有一个根")
    if any(target not in seen or old in seen for old, target in data.get("aliases", {}).items()):
        raise ValueError("旧槽位映射无效")
    CoordinateSettings.parse({"sensor_axes": data["coordinates"]["sensor_axes"]})
    if data["coordinates"].get("quaternion") != "wxyz" or data["coordinates"].get("handedness") != "right":
        raise ValueError("当前求解器要求右手 WXYZ")
    for key, value in data["timing"].items():
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("时间配置必须为正")
    return data


def canonical_slot(config, slot, *, allow_alias=False):
    if slot in (None, "", "unassigned", "unknown"):
        return None
    slots = {item["id"] for item in config["segments"]}
    if slot in slots:
        return slot
    if allow_alias and slot in config.get("aliases", {}):
        return config["aliases"][slot]
    raise ValueError("未知身体位置；旧别名需显式启用版本化映射")
