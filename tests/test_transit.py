import json
import threading
import urllib.request

import pytest

from raspberrypi_env_station.config import parse_config
from raspberrypi_env_station.dashboard import make_server
from raspberrypi_env_station.transit import (
    TransitCache,
    TransitConfig,
    fetch_flights,
    fetch_trains,
    normalize_flight,
    normalize_train,
    railway_operator,
    sources,
)

# ODPT の実データ（2026-11-23）と同じ形の例
FLIGHT_DELAYED = {
    "dc:date": "2026-11-23T10:26:02+09:00",
    "odpt:airline": "odpt.Operator:JAL",
    "odpt:operator": "odpt.Operator:JAL",
    "odpt:flightNumber": ["JL510"],
    "odpt:flightStatus": "odpt.FlightStatus:EstimatedDeparture",
    "odpt:departureGate": "16",
    "odpt:departureAirport": "odpt.Airport:CTS",
    "odpt:destinationAirport": "odpt.Airport:HND",
    "odpt:scheduledDepartureTime": "10:55",
    "odpt:estimatedDepartureTime": "16:55",
    "odpt:flightInformationSummary": {"en": "Delayed", "ja": "出発遅延"},
    "odpt:flightInformationText": {"en": "due to ...", "ja": "使用する飛行機の到着遅れのため"},
}
FLIGHT_ON_TIME = {
    "odpt:operator": "odpt.Operator:ANA",
    "odpt:flightNumber": ["NH60"],
    "odpt:departureAirport": "odpt.Airport:CTS",
    "odpt:destinationAirport": "odpt.Airport:HND",
    "odpt:scheduledDepartureTime": "12:00",
}
FLIGHT_OTHER_DEST = {**FLIGHT_ON_TIME, "odpt:destinationAirport": "odpt.Airport:ITM"}
TITLES = {"odpt.FlightStatus:EstimatedDeparture": "出発予定", "odpt.FlightStatus:Cancelled": "欠航"}

TRAIN_NORMAL = {
    "odpt:railway": "odpt.Railway:TokyoMetro.Marunouchi",
    "odpt:trainInformationText": {"ja": "現在、平常どおり運転しています。", "en": "Normal service"},
    "dc:date": "2026-11-23T11:04:00+09:00",
}
TRAIN_DELAYED = {
    "odpt:railway": "odpt.Railway:Toei.Asakusa",
    "odpt:trainInformationStatus": {"ja": "遅延"},
    "odpt:trainInformationText": {"ja": "人身事故の影響で遅れが出ています。"},
    "odpt:trainInformationCause": {"ja": "人身事故"},
}


class FakeClient:
    """ODPT の代わり。呼ばれた内容を記録し、決めた値を返す。"""

    def __init__(self, responses, fail=False):
        self.responses = responses
        self.calls = []
        self.fail = fail

    def get(self, rdf_type, params, public=False):
        self.calls.append((rdf_type, params, public))
        if self.fail:
            raise RuntimeError("ODPT odpt:FlightInformationDeparture: HTTP 503")
        return self.responses(rdf_type, params)


def test_normalize_flight_keeps_status_and_texts():
    f = normalize_flight(FLIGHT_DELAYED, TITLES)
    assert f["number"] == "JL510"
    assert (f["from"], f["to"], f["airline"]) == ("CTS", "HND", "JAL")
    assert (f["scheduled"], f["estimated"], f["gate"]) == ("10:55", "16:55", "16")
    assert (f["status"], f["status_ja"], f["summary"]) == (
        "EstimatedDeparture",
        "出発予定",
        "出発遅延",
    )


def test_normalize_flight_on_time_has_no_status():
    f = normalize_flight(FLIGHT_ON_TIME, TITLES)
    assert f["status"] is None and f["status_ja"] is None and f["summary"] is None
    assert f["airline"] == "ANA"  # odpt:airline がなければ odpt:operator を使う


def test_normalize_train():
    assert normalize_train(TRAIN_NORMAL, {"odpt.Railway:TokyoMetro.Marunouchi": "丸ノ内線"}) == {
        "railway": "odpt.Railway:TokyoMetro.Marunouchi",
        "name": "丸ノ内線",
        "operator": "TokyoMetro",
        "status": None,
        "text": "現在、平常どおり運転しています。",
        "cause": None,
        "date": "2026-11-23T11:04:00+09:00",
    }
    t = normalize_train(TRAIN_DELAYED, {})
    assert (t["name"], t["status"], t["cause"]) == ("Toei.Asakusa", "遅延", "人身事故")


def test_railway_operator():
    assert railway_operator("odpt.Railway:TokyoMetro.MarunouchiBranch") == "TokyoMetro"
    assert railway_operator("odpt.Railway:Toei.Oedo") == "Toei"


def test_fetch_flights_keeps_only_configured_routes():
    client = FakeClient(lambda t, p: [FLIGHT_DELAYED, FLIGHT_ON_TIME, FLIGHT_OTHER_DEST])
    cfg = TransitConfig(odpt_token="x", flight_routes=(("CTS", "HND"),), airlines=("JAL",))
    flights = fetch_flights(client, cfg, TITLES)
    assert [f["number"] for f in flights] == ["JL510", "NH60"]  # 伊丹行きは除く・定刻順
    assert client.calls == [
        (
            "odpt:FlightInformationDeparture",
            {"odpt:operator": "odpt.Operator:JAL", "odpt:departureAirport": "odpt.Airport:CTS"},
            False,
        )
    ]


def test_fetch_trains_uses_public_api_for_toei_and_keeps_config_order():
    def responses(rdf_type, params):
        return {"odpt.Operator:TokyoMetro": [TRAIN_NORMAL], "odpt.Operator:Toei": [TRAIN_DELAYED]}[
            params["odpt:operator"]
        ]

    client = FakeClient(responses)
    cfg = TransitConfig(
        odpt_token="x",
        railways=("odpt.Railway:Toei.Asakusa", "odpt.Railway:TokyoMetro.Marunouchi"),
    )
    trains = fetch_trains(client, cfg, {})
    assert [t["railway"] for t in trains] == list(cfg.railways)
    public = {c[1]["odpt:operator"]: c[2] for c in client.calls}
    assert public == {"odpt.Operator:Toei": True, "odpt.Operator:TokyoMetro": False}


def test_refresh_keeps_last_values_on_error():
    ok = FakeClient(lambda t, p: [] if t != "odpt:TrainInformation" else [TRAIN_NORMAL])
    cfg = TransitConfig(odpt_token="x", railways=("odpt.Railway:TokyoMetro.Marunouchi",))
    cache = TransitCache(cfg, ok)
    cache.refresh()
    first = cache.snapshot()
    assert first.error is None and len(first.trains) == 1
    cache.client = FakeClient(None, fail=True)
    cache.refresh()
    second = cache.snapshot()
    assert second.trains == first.trains and second.fetched_at == first.fetched_at
    assert "503" in second.error


def test_enabled_and_sources():
    assert not TransitConfig().enabled
    assert not TransitConfig(flight_routes=(("CTS", "HND"),)).enabled  # トークンがない
    assert TransitConfig(railways=("odpt.Railway:Toei.Asakusa",)).enabled  # 都営はトークン不要
    cfg = TransitConfig(
        odpt_token="x",
        flight_routes=(("CTS", "HND"),),
        railways=("odpt.Railway:TokyoMetro.Ginza", "odpt.Railway:Toei.Oedo"),
    )
    assert sources(cfg) == ["日本航空", "全日本空輸", "東京メトロ", "東京都交通局"]


@pytest.mark.parametrize(
    "transit",
    [
        {"flight_routes": [["CTS"]]},
        {"flight_routes": [["CTS", "HANEDA"]]},
        {"airlines": ["ADO"]},
        {"railways": ["TokyoMetro.Ginza"]},
        {"interval_s": 10},
    ],
)
def test_parse_transit_rejects_bad_values(transit):
    with pytest.raises(ValueError):
        parse_config({"transit": transit})


def test_parse_transit():
    cfg = parse_config(
        {
            "transit": {
                "odpt_token": "secret",
                "flight_routes": [["cts", "hnd"]],
                "railways": ["odpt.Railway:Toei.Asakusa"],
                "contact": "総務まで",
            }
        }
    ).transit
    assert cfg.flight_routes == (("CTS", "HND"),)
    assert cfg.airlines == ("JAL", "ANA")
    assert (cfg.interval_s, cfg.contact) == (300, "総務まで")


def test_api_transit(tmp_path):
    config = parse_config(
        {
            "database": str(tmp_path / "none.sqlite"),
            "transit": {
                "odpt_token": "secret",
                "railways": ["odpt.Railway:TokyoMetro.Marunouchi"],
                "contact": "総務",
            },
        }
    )
    cache = TransitCache(
        config.transit, FakeClient(lambda t, p: [TRAIN_NORMAL] if "Train" in t else [])
    )
    cache.refresh()
    srv = make_server(config, tmp_path, "127.0.0.1", 0, cache)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/transit"
        with urllib.request.urlopen(url) as res:
            body = json.load(res)
        assert body["enabled"] is True
        assert body["trains"][0]["text"] == "現在、平常どおり運転しています。"
        assert body["sources"] == ["東京メトロ"] and body["contact"] == "総務"
        assert body["fetched_at"] is not None and body["error"] is None
        assert "secret" not in json.dumps(body)
    finally:
        srv.shutdown()
        srv.server_close()


def test_api_transit_disabled(tmp_path):
    config = parse_config({"database": str(tmp_path / "none.sqlite")})
    srv = make_server(config, tmp_path, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/transit"
        with urllib.request.urlopen(url) as res:
            assert json.load(res) == {"enabled": False}
    finally:
        srv.shutdown()
        srv.server_close()


def test_without_token_only_public_railways_are_used():
    cfg = TransitConfig(
        flight_routes=(("CTS", "HND"),),
        railways=("odpt.Railway:TokyoMetro.Ginza", "odpt.Railway:Toei.Asakusa"),
    )
    assert cfg.usable_railways == ("odpt.Railway:Toei.Asakusa",)
    assert sources(cfg) == ["東京都交通局"]
    client = FakeClient(lambda t, p: [TRAIN_DELAYED])
    cache = TransitCache(cfg, client)
    cache.refresh()
    snap = cache.snapshot()
    assert snap.error is None and [t["railway"] for t in snap.trains] == [
        "odpt.Railway:Toei.Asakusa"
    ]
    assert all(public for _, _, public in client.calls)  # トークンの要る API は呼ばない
