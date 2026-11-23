"""TOML 設定ファイルの読み込み。"""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from raspberrypi_env_station.transit import TransitConfig
from raspberrypi_env_station.weather import WeatherArea


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
class Office:
    """ダッシュボードの地図に並べる拠点（札幌・東京など）。WGS84。"""

    name: str
    latitude: float
    longitude: float
    label: str = ""  # 地図の札に添える英字（SAPPORO など）
    # MapLibre のズーム。512px のタイルが基準なので、地理院タイル（256px）のズームより 1 小さい
    zoom: float = 12
    weather: WeatherArea | None = None  # 天気予報と警報・注意報（気象庁）


@dataclass(frozen=True)
class DashboardConfig:
    """大型モニター用ダッシュボードの設定。"""

    host: str = "127.0.0.1"  # 共用 Wi-Fi から開けないよう Pi 自身だけで待ち受ける
    port: int = 8080
    offices: tuple[Office, ...] = ()  # 空なら設置場所（station）を 1 つだけ出す


@dataclass(frozen=True)
class Config:
    database: Path
    interval_s: float
    sensors: list[SensorConfig]
    station: Station | None = None
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    transit: TransitConfig = field(default_factory=TransitConfig)


_KNOWN_TYPES = {"scd4x"}


def parse_station(data: dict[str, Any] | None) -> Station | None:
    if not data:
        return None
    lat, lon = float(data["latitude"]), float(data["longitude"])
    _check_lat_lon(lat, lon)
    return Station(name=str(data.get("name", "")), latitude=lat, longitude=lon)


def _check_lat_lon(lat: float, lon: float) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"緯度経度が範囲外です: {lat}, {lon}")


def parse_office(data: dict[str, Any]) -> Office:
    lat, lon = float(data["latitude"]), float(data["longitude"])
    _check_lat_lon(lat, lon)
    zoom = float(data.get("zoom", 12))
    if not 0 <= zoom <= 18:
        raise ValueError(f"zoom は 0〜18 にしてください: {zoom}")
    return Office(
        name=str(data["name"]),
        latitude=lat,
        longitude=lon,
        label=str(data.get("label", "")),
        zoom=zoom,
        weather=parse_weather_area(data.get("weather")),
    )


_CODE_LENGTHS = {"office": 6, "area": 6, "station": 5, "city": 7}


def parse_weather_area(data: dict[str, Any] | None) -> WeatherArea | None:
    if not data:
        return None
    codes = {k: str(data.get(k, "")) for k in _CODE_LENGTHS}
    if bad := [k for k, n in _CODE_LENGTHS.items() if not re.fullmatch(rf"\d{{{n}}}", codes[k])]:
        raise ValueError(f"weather の {bad} は気象庁のコード（数字）にしてください: {codes}")
    return WeatherArea(**codes)


MAX_OFFICES = 2  # 画面の上半分に並べられる数


def parse_dashboard(data: dict[str, Any] | None) -> DashboardConfig:
    if not data:
        return DashboardConfig()
    offices = tuple(parse_office(o) for o in data.get("offices", []))
    if len(offices) > MAX_OFFICES:
        raise ValueError(f"dashboard.offices は {MAX_OFFICES} つまでにしてください")
    return DashboardConfig(
        host=str(data.get("host", "127.0.0.1")),
        port=int(data.get("port", 8080)),
        offices=offices,
    )


AIRLINES = ("JAL", "ANA")  # ODPT で運航情報が取れる航空会社


def parse_transit(data: dict[str, Any] | None) -> TransitConfig:
    if not data:
        return TransitConfig()
    routes = []
    for route in data.get("flight_routes", []):
        if len(route) != 2 or not all(isinstance(c, str) and len(c) == 3 for c in route):
            raise ValueError(f"flight_routes は [出発, 到着] の空港コード（3 文字）: {route}")
        routes.append((route[0].upper(), route[1].upper()))
    airlines = tuple(data.get("airlines", AIRLINES))
    if unknown := [a for a in airlines if a not in AIRLINES]:
        raise ValueError(f"未対応の航空会社: {unknown}（{list(AIRLINES)} から選ぶ）")
    railways = tuple(data.get("railways", []))
    if bad := [r for r in railways if not str(r).startswith("odpt.Railway:")]:
        raise ValueError(f"railways は odpt.Railway: で始まる ID にしてください: {bad}")
    interval = float(data.get("interval_s", 300))
    if interval < 60:
        raise ValueError("transit.interval_s は 60 秒以上にしてください（ODPT に負荷をかけない）")
    return TransitConfig(
        odpt_token=str(data.get("odpt_token", "")),
        interval_s=interval,
        flight_routes=tuple(routes),
        airlines=airlines,
        railways=railways,
        contact=str(data.get("contact", "")),
    )


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
        dashboard=parse_dashboard(data.get("dashboard")),
        transit=parse_transit(data.get("transit")),
    )


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        return parse_config(tomllib.load(f))
