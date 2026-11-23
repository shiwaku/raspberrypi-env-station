import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from raspberrypi_env_station.config import parse_config
from raspberrypi_env_station.dashboard import downsample, make_server
from raspberrypi_env_station.storage import Storage


@pytest.fixture
def server(tmp_path):
    db = tmp_path / "readings.sqlite"
    storage = Storage(db)
    now = datetime.now(UTC)
    storage.write(now - timedelta(hours=30), "scd4x", {"co2_ppm": 400.0})  # 24 時間より前
    storage.write(now - timedelta(minutes=2), "scd4x", {"co2_ppm": 600.0, "temperature_c": 21.5})
    storage.write(now - timedelta(minutes=1), "scd4x", {"co2_ppm": 650.0})
    storage.close()

    web = tmp_path / "build"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (web / "app.js").write_text("export {}", encoding="utf-8")

    config = parse_config(
        {
            "database": str(db),
            "station": {"name": "オフィス", "latitude": 43.06, "longitude": 141.35},
            "dashboard": {
                "offices": [
                    {"name": "札幌", "label": "SAPPORO", "latitude": 43.06, "longitude": 141.35},
                    {"name": "東京", "latitude": 35.68, "longitude": 139.77, "zoom": 11},
                ]
            },
        }
    )
    srv = make_server(config, web, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(url):
    with urllib.request.urlopen(url) as res:
        return res.status, res.headers["Content-Type"], res.read()


def get_json(url):
    return json.loads(get(url)[2])


def test_config(server):
    body = get_json(f"{server}/api/config")
    assert body["station"] == {"name": "オフィス", "latitude": 43.06, "longitude": 141.35}
    assert body["offices"] == [
        {"name": "札幌", "label": "SAPPORO", "latitude": 43.06, "longitude": 141.35, "zoom": 12},
        {"name": "東京", "label": "", "latitude": 35.68, "longitude": 139.77, "zoom": 11},
    ]


def test_latest_per_metric(server):
    body = get_json(f"{server}/api/latest")
    assert body["co2_ppm"] == 650.0
    assert body["temperature_c"] == 21.5
    assert body["humidity_pct"] is None


def test_series_limits_to_hours(server):
    body = get_json(f"{server}/api/series?metric=co2_ppm&hours=24")
    assert [v for _, v in body["points"]] == [600.0, 650.0]


@pytest.mark.parametrize(
    "query", ["metric=bogus", "metric=co2_ppm&hours=0", "metric=co2_ppm&hours=x"]
)
def test_series_rejects_bad_query(server, query):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{server}/api/series?{query}")
    assert exc.value.code == 400


def test_static_files_and_fallback(server):
    status, ctype, _ = get(f"{server}/app.js")
    assert (status, ctype) == (200, "text/javascript")
    assert get(f"{server}/somewhere")[2].startswith(b"<!doctype html>")
    with pytest.raises(urllib.error.HTTPError) as exc:  # web/build の外は読ませない
        get(f"{server}/../../etc/passwd")
    assert exc.value.code == 404


def test_missing_database_returns_empty(tmp_path):
    config = parse_config({"database": str(tmp_path / "none.sqlite")})
    srv = make_server(config, tmp_path, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        assert get_json(f"{base}/api/latest")["co2_ppm"] is None
        assert get_json(f"{base}/api/series?metric=co2_ppm")["points"] == []
        assert get_json(f"{base}/api/config") == {"station": None, "offices": []}
    finally:
        srv.shutdown()
        srv.server_close()


def test_downsample_averages_chunks():
    points = [(str(i), float(i)) for i in range(10)]
    assert downsample(points, 5) == [("0", 0.5), ("2", 2.5), ("4", 4.5), ("6", 6.5), ("8", 8.5)]
    assert downsample(points, 20) == points


def test_offices_default_to_station(tmp_path):
    config = parse_config(
        {
            "database": str(tmp_path / "none.sqlite"),
            "station": {"name": "オフィス", "latitude": 43.06, "longitude": 141.35},
        }
    )
    srv = make_server(config, tmp_path, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = get_json(f"http://127.0.0.1:{srv.server_address[1]}/api/config")
        assert body["offices"] == [
            {"name": "オフィス", "latitude": 43.06, "longitude": 141.35, "label": "", "zoom": 12}
        ]
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.parametrize(
    "offices",
    [
        [{"name": "札幌", "latitude": 143.06, "longitude": 141.35}],  # 緯度が範囲外
        [{"name": "札幌", "latitude": 43.06, "longitude": 141.35, "zoom": 25}],
        [{"name": n, "latitude": 35.0, "longitude": 139.0} for n in "ABC"],  # 3 つ以上
    ],
)
def test_parse_dashboard_rejects_bad_offices(offices):
    with pytest.raises(ValueError):
        parse_config({"dashboard": {"offices": offices}})
