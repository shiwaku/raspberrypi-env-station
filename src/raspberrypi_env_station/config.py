"""TOML 設定ファイルの読み込み。"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SensorConfig:
    type: str  # "scd4x"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Station:
    """設置場所。固定設置なので GPS ではなく設定ファイルに書く（WGS84）。"""

    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Config:
    database: Path
    interval_s: float
    sensors: list[SensorConfig]
    station: Station | None = None


_KNOWN_TYPES = {"scd4x"}


def parse_station(data: dict[str, Any] | None) -> Station | None:
    if not data:
        return None
    lat, lon = float(data["latitude"]), float(data["longitude"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"緯度経度が範囲外です: {lat}, {lon}")
    return Station(name=str(data.get("name", "")), latitude=lat, longitude=lon)


def parse_config(data: dict[str, Any]) -> Config:
    interval = float(data.get("interval_s", 60))
    if interval <= 0:
        raise ValueError("interval_s は正の数にしてください")
    sensors = []
    for entry in data.get("sensors", []):
        entry = dict(entry)
        sensor_type = entry.pop("type", None)
        if sensor_type not in _KNOWN_TYPES:
            raise ValueError(f"未対応のセンサー種別: {sensor_type!r}（{sorted(_KNOWN_TYPES)}）")
        if entry.pop("enabled", True):
            sensors.append(SensorConfig(type=sensor_type, options=entry))
    return Config(
        database=Path(data.get("database", "data/readings.sqlite")),
        interval_s=interval,
        sensors=sensors,
        station=parse_station(data.get("station")),
    )


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        return parse_config(tomllib.load(f))
