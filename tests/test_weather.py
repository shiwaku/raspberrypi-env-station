"""気象庁防災情報 XML（2026-11-23 の実際の電文）で、天気予報と警報・注意報の読み取りを確かめる。"""

import json
import threading
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from raspberrypi_env_station.config import parse_config
from raspberrypi_env_station.dashboard import make_server, make_weather
from raspberrypi_env_station.weather import (
    WeatherArea,
    WeatherCache,
    latest_links,
    parse_duration,
    parse_forecast,
    parse_warnings,
    summarize,
)

DATA = Path(__file__).parent / "data" / "jma"
SAPPORO = WeatherArea(office="016000", area="016010", station="14163", city="0110000")
TOKYO = WeatherArea(office="130000", area="130010", station="44132", city="1310100")
JST = datetime.fromisoformat("2026-11-23T12:00:00+09:00").tzinfo


def at(hhmm: str, day: int = 23) -> datetime:
    return datetime.fromisoformat(f"2026-11-{day}T{hhmm}:00+09:00")


def read(name: str) -> bytes:
    return (DATA / name).read_bytes()


def test_parse_duration():
    assert parse_duration("PT6H") == timedelta(hours=6)
    assert parse_duration("P1D") == timedelta(days=1)
    assert parse_duration("P2DT13H") == timedelta(days=2, hours=13)
    with pytest.raises(ValueError):
        parse_duration("6 hours")


def test_parse_forecast_sapporo():
    f = parse_forecast(read("VPFD51_016000.xml"), SAPPORO.area, SAPPORO.station)
    assert f["report_time"] == "2026-11-23T11:00:00+09:00"
    assert [(w["name"], w["text"]) for w in f["weather"]] == [
        ("今日", "晴れ後雨"),
        ("明日", "雨後雪"),
        ("明後日", "くもり一時雪"),
    ]
    assert [p["value"] for p in f["pops"]] == [20, 50, 90, 70, 50, 40]
    assert f["pops"][0]["name"] == "１２時から１８時まで"
    assert ("日中の最高気温", 7) in [(t["type"], t["value"]) for t in f["temps"]]


def test_parse_forecast_ignores_other_areas():
    f = parse_forecast(read("VPFD51_016000.xml"), "999999", "99999")
    assert f["weather"] == [] and f["pops"] == [] and f["temps"] == []


def test_parse_warnings():
    w = parse_warnings(read("VPWW54_016000.xml"), SAPPORO.city)
    assert w["items"] == [{"name": "雷注意報", "status": "継続"}]
    t = parse_warnings(read("VPWW54_130000.xml"), TOKYO.city)
    assert t["items"] == [{"name": "乾燥注意報", "status": "継続"}]


def test_summarize_picks_current_and_upcoming():
    f = parse_forecast(read("VPFD51_016000.xml"), SAPPORO.area, SAPPORO.station)
    w = parse_warnings(read("VPWW54_016000.xml"), SAPPORO.city)
    s = summarize(f, w, at("13:00"))
    assert s["weather"] == {"text": "晴れ後雨", "label": "今日"}
    assert s["pop"] == {"value": 20, "label": "１２時から１８時まで"}
    assert s["high"] == {"value": 7, "label": "今日日中"}
    assert s["low"] == {"value": 6, "label": "明日朝"}
    assert s["warnings"] == [{"name": "雷注意報", "status": "継続", "level": "advisory"}]
    # 夕方になると、降水確率と最高気温は次の時間帯に進む
    later = summarize(f, w, at("19:00"))
    assert later["pop"]["label"] == "１８時から００時まで"
    assert later["high"]["label"] == "明日日中"


def test_summarize_without_data():
    s = summarize(None, None, at("13:00"))
    assert s["weather"] is None and s["warnings"] is None


def test_warning_levels():
    s = summarize(
        None,
        {
            "report_time": None,
            "items": [
                {"name": "大雪警報", "status": "発表"},
                {"name": "大雨特別警報", "status": "発表"},
                {"name": "強風注意報", "status": "継続"},
            ],
        },
        at("13:00"),
    )
    assert [w["level"] for w in s["warnings"]] == ["warning", "emergency", "advisory"]


FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>t</title><link type="application/xml" href="https://www.data.jma.go.jp/developer/xml/data/20261123013853_0_VPFD51_016000.xml"/></entry>
<entry><title>t</title><link type="application/xml" href="https://www.data.jma.go.jp/developer/xml/data/20261122193952_0_VPFD51_016000.xml"/></entry>
<entry><title>t</title><link type="application/xml" href="https://www.data.jma.go.jp/developer/xml/data/20261123015744_0_VPWW54_016000.xml"/></entry>
<entry><title>t</title><link type="application/xml" href="https://www.data.jma.go.jp/developer/xml/data/20261123013510_0_VPFD51_130000.xml"/></entry>
</feed>"""


def test_latest_links_picks_newest_per_kind_and_office():
    links = latest_links(FEED, {("VPFD51", "016000"), ("VPWW54", "016000")})
    assert links == {
        (
            "VPFD51",
            "016000",
        ): "https://www.data.jma.go.jp/developer/xml/data/20261123013853_0_VPFD51_016000.xml",
        (
            "VPWW54",
            "016000",
        ): "https://www.data.jma.go.jp/developer/xml/data/20261123015744_0_VPWW54_016000.xml",
    }


class FakeJma:
    """気象庁の代わり。フィードと電文を返し、取った URL を記録する。"""

    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url.endswith("/feed/regular_l.xml") or url.endswith("/feed/regular.xml"):
            return FEED
        if "/feed/" in url:
            return b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        name = url.rsplit("_0_", 1)[1]
        return read(name)


def test_cache_fetches_each_report_once():
    jma = FakeJma()
    cache = WeatherCache({"札幌": SAPPORO}, get=jma)
    cache.refresh()
    assert cache.error is None
    s = cache.summary("札幌", at("13:00"))
    assert s["weather"]["text"] == "晴れ後雨" and s["warnings"] == [
        {"name": "雷注意報", "status": "継続", "level": "advisory"}
    ]
    assert jma.calls[:2] == [
        "https://www.data.jma.go.jp/developer/xml/feed/regular_l.xml",
        "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml",
    ]
    reports = [c for c in jma.calls if "/data/" in c]
    assert len(reports) == 2
    # 2 回目は高頻度フィードを見て、同じ電文は取り直さない
    jma.calls.clear()
    cache.refresh()
    assert all("/feed/" in c and "_l.xml" not in c for c in jma.calls)


def test_cache_keeps_values_on_error():
    jma = FakeJma()
    cache = WeatherCache({"札幌": SAPPORO}, get=jma)
    cache.refresh()

    def broken(url):
        raise OSError("network down")

    cache.get = broken
    cache.refresh()
    assert "network down" in cache.error
    assert cache.summary("札幌", at("13:00"))["weather"]["text"] == "晴れ後雨"


def test_config_weather_and_api(tmp_path):
    config = parse_config(
        {
            "database": str(tmp_path / "none.sqlite"),
            "dashboard": {
                "offices": [
                    {
                        "name": "札幌",
                        "latitude": 43.06,
                        "longitude": 141.35,
                        "weather": {
                            "office": "016000",
                            "area": "016010",
                            "station": "14163",
                            "city": "0110000",
                        },
                    },
                    {"name": "東京", "latitude": 35.69, "longitude": 139.76},
                ]
            },
        }
    )
    cache = make_weather(config)
    assert cache is not None and list(cache.areas) == ["札幌"]
    cache.get = FakeJma()
    cache.refresh()
    srv = make_server(config, tmp_path, "127.0.0.1", 0, weather=cache)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/weather"
        with urllib.request.urlopen(url) as res:
            body = json.load(res)
        assert list(body["offices"]) == ["札幌"]
        assert body["offices"]["札幌"]["warnings"][0]["name"] == "雷注意報"
        assert body["error"] is None and body["fetched_at"] is not None
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.parametrize(
    "weather",
    [
        {"office": "16000", "area": "016010", "station": "14163", "city": "0110000"},
        {"office": "016000", "area": "016010", "station": "14163"},
        {"office": "016000", "area": "016010", "station": "abcde", "city": "0110000"},
    ],
)
def test_config_rejects_bad_weather_codes(weather):
    with pytest.raises(ValueError):
        parse_config(
            {
                "dashboard": {
                    "offices": [
                        {"name": "札幌", "latitude": 43.0, "longitude": 141.0, "weather": weather}
                    ]
                }
            }
        )
