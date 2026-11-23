"""拠点ごとの天気予報と警報・注意報を、気象庁防災情報 XML から取る。

- 天気・降水確率・最高／最低気温: 府県天気予報（VPFD51、定時フィード）
- 警報・注意報: 気象警報・注意報（H27 形式、VPWW54、随時フィード）の市町村ごとの欄

気象庁は「一度取得したファイルを再取得しない」実装を求めているので、フィード（2 分ごと）を見て、
拠点の新しい電文が出たときだけ取る。起動時は長期フィードから最新の電文を探す。
出典: 気象庁防災情報 XML（https://xml.kishou.go.jp/）。公共データ利用規約に従い出典を画面に出す。
"""

import logging
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger("raspberrypi_env_station.weather")

FEED = "https://www.data.jma.go.jp/developer/xml/feed/{}.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
TIMEOUT_S = 30
NO_WARNING = "発表警報・注意報はなし"


@dataclass(frozen=True)
class WeatherArea:
    """拠点の気象の取り方。コードは気象庁の予報区・地点・市町村のコード。"""

    office: str  # 府県予報区（電文のファイル名の末尾。札幌は 016000、東京は 130000）
    area: str  # 天気・降水確率の区域（一次細分区域。石狩地方は 016010）
    station: str  # 気温の地点（札幌は 14163）
    city: str  # 警報・注意報の市町村（札幌市は 0110000）


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el: ET.Element, *path: str) -> ET.Element | None:
    """名前空間を気にせず、子をたどる。"""
    for name in path:
        el = next((c for c in el if _local(c.tag) == name), None)  # type: ignore[assignment]
        if el is None:
            return None
    return el


def _iter(el: ET.Element, name: str):
    return (c for c in el.iter() if _local(c.tag) == name)


def _text(el: ET.Element | None) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def parse_duration(value: str) -> timedelta:
    """P1D・PT6H・P2DT13H などの期間。"""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", value or "")
    if not m:
        raise ValueError(f"期間が読めない: {value}")
    d, h, mi = (int(x or 0) for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def _time_defines(series: ET.Element) -> dict[str, dict[str, Any]]:
    out = {}
    defines = _find(series, "TimeDefines")
    for td in [] if defines is None else list(defines):
        start = datetime.fromisoformat(_text(_find(td, "DateTime")) or "")
        out[td.get("timeId", "")] = {
            "start": start,
            "end": start + parse_duration(_text(_find(td, "Duration")) or "PT0H"),
            "name": _text(_find(td, "Name")),
        }
    return out


def _report_time(root: ET.Element) -> str | None:
    return _text(_find(root, "Head", "ReportDateTime"))


def parse_forecast(data: bytes, area: str, station: str) -> dict[str, Any]:
    """VPFD51 から、区域の天気・降水確率と、地点の気温を取り出す。"""
    root = ET.fromstring(data)
    weather: list[dict] = []
    pops: list[dict] = []
    temps: list[dict] = []
    for infos in _iter(root, "MeteorologicalInfos"):
        if infos.get("type") not in ("区域予報", "地点予報"):
            continue
        for series in (c for c in infos if _local(c.tag) == "TimeSeriesInfo"):
            # 日ごとの予報だけを使う。3 時間ごとの時系列は時刻に名前（今日・明日など）がない
            times = {k: v for k, v in _time_defines(series).items() if v["name"]}
            for item in (c for c in series if _local(c.tag) == "Item"):
                where = _find(item, "Area")
                if where is None:
                    where = _find(item, "Station")
                code = _text(_find(where, "Code")) if where is not None else None
                if code == area:
                    for w in _iter(item, "Weather"):
                        if w.get("type") == "天気" and w.get("refID") in times:
                            weather.append({**times[w.get("refID", "")], "text": _text(w)})
                    for p in _iter(item, "ProbabilityOfPrecipitation"):
                        if p.get("refID") in times and _text(p) is not None:
                            pops.append({**times[p.get("refID", "")], "value": int(_text(p) or 0)})
                if code == station:
                    for t in _iter(item, "Temperature"):
                        if t.get("refID") in times and _text(t) is not None:
                            temps.append(
                                {
                                    **times[t.get("refID", "")],
                                    "type": t.get("type"),
                                    "value": int(_text(t) or 0),
                                }
                            )
    return {"report_time": _report_time(root), "weather": weather, "pops": pops, "temps": temps}


def parse_warnings(data: bytes, city: str) -> dict[str, Any]:
    """VPWW54 の市町村ごとの欄から、その市町村に出ている警報・注意報（解除を除く）を取り出す。"""
    root = ET.fromstring(data)
    items: list[dict] = []
    for warning in _iter(root, "Warning"):
        if warning.get("type") != "気象警報・注意報（市町村等）":
            continue
        for item in (c for c in warning if _local(c.tag) == "Item"):
            if _text(_find(item, "Area", "Code")) != city:
                continue
            for kind in (c for c in item if _local(c.tag) == "Kind"):
                name, status = _text(_find(kind, "Name")), _text(_find(kind, "Status"))
                if name and name != NO_WARNING and status != "解除":
                    items.append({"name": name, "status": status})
    return {"report_time": _report_time(root), "items": items}


def _level(name: str) -> str:
    if "特別警報" in name:
        return "emergency"
    if "警報" in name:
        return "warning"
    return "advisory"


def summarize(
    forecast: dict[str, Any] | None, warnings: dict[str, Any] | None, now: datetime
) -> dict:
    """画面の帯に出す形にする。今にいちばん近い天気・降水確率と、これからの最高・最低気温。"""
    out: dict[str, Any] = {"weather": None, "pop": None, "high": None, "low": None}
    if forecast:

        def first(items, pred=lambda x: True):
            # 今を含むか、これからのもの
            return next((x for x in items if x["end"] > now and pred(x)), None)

        if w := first(forecast["weather"]):
            out["weather"] = {"text": w["text"], "label": w["name"]}
        if p := first(forecast["pops"]):
            out["pop"] = {"value": p["value"], "label": p["name"]}
        if h := first(forecast["temps"], lambda t: t["type"] == "日中の最高気温"):
            out["high"] = {"value": h["value"], "label": h["name"]}
        if lo := first(forecast["temps"], lambda t: t["type"] == "朝の最低気温"):
            out["low"] = {"value": lo["value"], "label": lo["name"]}
        out["forecast_time"] = forecast["report_time"]
    out["warnings"] = (
        [{**w, "level": _level(w["name"])} for w in warnings["items"]] if warnings else None
    )
    out["warning_time"] = warnings["report_time"] if warnings else None
    return out


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "raspberrypi-env-station"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
        return res.read()


def latest_links(feed: bytes, kinds_offices: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """フィードから、(電文の種類, 府県予報区) ごとに最新の電文の URL を探す。"""
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for entry in ET.fromstring(feed).iter(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link")
        href = link.get("href", "") if link is not None else ""
        m = re.search(r"/(\d{14})_\d+_(VP[A-Z]{2}\d{2})_(\d{6})\.xml$", href)
        if not m or (m[2], m[3]) not in kinds_offices:
            continue
        key = (m[2], m[3])
        if key not in out or m[1] > out[key][0]:  # ファイル名の時刻が新しいものを使う
            out[key] = (m[1], href)
    return {k: v[1] for k, v in out.items()}


class WeatherCache:
    """気象庁のフィードを見て、拠点の新しい電文だけ取り、解析した値を持っておく。"""

    POLL_S = 120  # 高頻度フィードは直近 10 分以上を載せるので、2 分ごとなら取りこぼさない

    def __init__(self, areas: dict[str, WeatherArea], get=_get) -> None:
        self.areas = areas  # 拠点名 -> 取り方
        self.get = get
        self._lock = threading.Lock()
        self._forecasts: dict[str, dict] = {}
        self._warnings: dict[str, dict] = {}
        self._fetched: dict[tuple[str, str], str] = {}  # (種類, 府県予報区) -> 取った URL
        self._initialized = False
        self.fetched_at: float | None = None
        self.error: str | None = None
        self._stop = threading.Event()

    def _wanted(self) -> set[tuple[str, str]]:
        return {(k, a.office) for a in self.areas.values() for k in ("VPFD51", "VPWW54")}

    def refresh(self) -> None:
        try:
            suffix = "" if self._initialized else "_l"  # 起動時だけ長期フィードを見る
            links: dict[tuple[str, str], str] = {}
            for feed in ("regular", "extra"):
                links.update(latest_links(self.get(FEED.format(feed + suffix)), self._wanted()))
            for key, url in links.items():
                if self._fetched.get(key) == url:
                    continue  # 同じ電文は取り直さない
                data = self.get(url)
                kind, office = key
                with self._lock:
                    for name, area in self.areas.items():
                        if area.office != office:
                            continue
                        if kind == "VPFD51":
                            self._forecasts[name] = parse_forecast(data, area.area, area.station)
                        else:
                            self._warnings[name] = parse_warnings(data, area.city)
                self._fetched[key] = url
            self._initialized = True
            self.fetched_at = time.time()
            self.error = None
        except Exception as e:  # 取れなかったときは前の値を残す
            log.warning("気象を取れませんでした: %s", e)
            self.error = str(e)

    def summary(self, name: str, now: datetime) -> dict | None:
        if name not in self.areas:
            return None
        with self._lock:
            return summarize(self._forecasts.get(name), self._warnings.get(name), now)

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self.POLL_S)

        threading.Thread(target=loop, name="weather", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
