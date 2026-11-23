"""飛行機と地下鉄の運行状況を、公共交通オープンデータセンター（ODPT）から取る。

- 飛行機: JAL・ANA のリアルタイム出発情報（odpt:FlightInformationDeparture）。
  api.odpt.org（公共交通オープンデータ基本ライセンス、要トークン）
- 地下鉄: 運行情報（odpt:TrainInformation）。東京メトロは api.odpt.org（要トークン）、
  都営は api-public.odpt.org（CC BY 4.0、トークン不要）

ODPT の規約に合わせて、取った値は加工しすぎず、データの時刻（dc:date）と出典を画面に出す。
取得は env-dashboard の中で interval_s ごとに 1 回だけ行い、画面からの問い合わせでは手元の値を返す。
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("raspberrypi_env_station.transit")

API = "https://api.odpt.org/api/v4"  # 基本ライセンス（要トークン）
PUBLIC_API = "https://api-public.odpt.org/api/v4"  # CC BY など（トークン不要）
PUBLIC_OPERATORS = {"Toei"}  # 公開 API で取れる事業者
TIMEOUT_S = 30

# 画面に出す空港名。ここにない空港はコードのまま出す
AIRPORTS = {
    "CTS": "新千歳",
    "HND": "羽田",
    "NRT": "成田",
    "ITM": "伊丹",
    "KIX": "関西",
    "NGO": "中部",
    "FUK": "福岡",
    "OKA": "那覇",
    "SDJ": "仙台",
    "HKD": "函館",
}

# 事業者の表示名（出典の表示に使う）
OPERATOR_NAMES = {
    "JAL": "日本航空",
    "ANA": "全日本空輸",
    "TokyoMetro": "東京メトロ",
    "Toei": "東京都交通局",
}


@dataclass(frozen=True)
class TransitConfig:
    odpt_token: str = ""  # api.odpt.org 用（チャレンジ用ではない）。リポジトリに入れない
    interval_s: float = 300  # ODPT の値は 5〜7 分ごとに更新される
    flight_routes: tuple[tuple[str, str], ...] = ()  # (出発空港, 到着空港) の IATA コード
    airlines: tuple[str, ...] = ("JAL", "ANA")
    railways: tuple[str, ...] = ()  # odpt.Railway:TokyoMetro.Marunouchi など
    contact: str = ""  # 画面に出す問い合わせ先（ODPT 基本ライセンス第 10 条 3 項）

    @property
    def usable_railways(self) -> tuple[str, ...]:
        """取れる路線。トークンがなければ、公開 API の事業者（都営）の路線だけ"""
        if self.odpt_token:
            return self.railways
        return tuple(r for r in self.railways if railway_operator(r) in PUBLIC_OPERATORS)

    @property
    def enabled(self) -> bool:
        return bool((self.flight_routes and self.odpt_token) or self.usable_railways)


def _ja(value: Any) -> str | None:
    """多言語の値（{"ja": ..., "en": ...}）から日本語を取り出す。"""
    if isinstance(value, dict):
        return value.get("ja") or value.get("en")
    return value if isinstance(value, str) else None


def _tail(odpt_id: str | None) -> str:
    """odpt.Airport:CTS -> CTS"""
    return (odpt_id or "").rsplit(":", 1)[-1]


def railway_operator(railway: str) -> str:
    """odpt.Railway:TokyoMetro.Marunouchi -> TokyoMetro"""
    return _tail(railway).split(".", 1)[0]


def normalize_flight(item: dict[str, Any], status_titles: dict[str, str]) -> dict[str, Any]:
    """FlightInformationDeparture の 1 件を、画面に出す形にする。"""
    status = item.get("odpt:flightStatus")
    numbers = item.get("odpt:flightNumber") or []
    return {
        "number": numbers[0] if numbers else "",
        "airline": _tail(item.get("odpt:airline") or item.get("odpt:operator")),
        "from": _tail(item.get("odpt:departureAirport")),
        "to": _tail(item.get("odpt:destinationAirport")),
        "scheduled": item.get("odpt:scheduledDepartureTime"),  # 現地時刻 HH:MM
        "estimated": item.get("odpt:estimatedDepartureTime"),
        "actual": item.get("odpt:actualDepartureTime"),
        "gate": item.get("odpt:departureGate"),
        "status": _tail(status) or None,  # Cancelled・Departed など。定刻なら None
        "status_ja": status_titles.get(status) if status else None,
        "summary": _ja(item.get("odpt:flightInformationSummary")),  # 出発遅延 など
        "text": _ja(item.get("odpt:flightInformationText")),
        "date": item.get("dc:date"),
    }


def normalize_train(item: dict[str, Any], titles: dict[str, str]) -> dict[str, Any]:
    """TrainInformation の 1 件を、画面に出す形にする。平常時は status が None。"""
    railway = item.get("odpt:railway") or ""
    return {
        "railway": railway,
        "name": titles.get(railway) or _tail(railway),
        "operator": railway_operator(railway),
        "status": _ja(item.get("odpt:trainInformationStatus")),
        "text": _ja(item.get("odpt:trainInformationText")),
        "cause": _ja(item.get("odpt:trainInformationCause")),
        "date": item.get("dc:date"),
    }


class OdptClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def get(self, rdf_type: str, params: dict[str, str], public: bool = False) -> list[dict]:
        query = dict(params)
        if not public:
            if not self.token:
                raise RuntimeError("ODPT のトークンが設定されていません（[transit] odpt_token）")
            query["acl:consumerKey"] = self.token
        url = f"{PUBLIC_API if public else API}/{rdf_type}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "raspberrypi-env-station"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
                return json.load(res)
        except urllib.error.HTTPError as e:
            # URL にトークンが入るので、エラーには URL を含めない
            raise RuntimeError(f"ODPT {rdf_type}: HTTP {e.code}") from None


@dataclass
class TransitSnapshot:
    flights: list[dict[str, Any]] = field(default_factory=list)
    trains: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: float | None = None  # time.time()
    error: str | None = None


def fetch_flights(client: OdptClient, config: TransitConfig, titles: dict[str, str]) -> list[dict]:
    out = []
    for origin in sorted({o for o, _ in config.flight_routes}):
        dests = {d for o, d in config.flight_routes if o == origin}
        for airline in config.airlines:
            items = client.get(
                "odpt:FlightInformationDeparture",
                {
                    "odpt:operator": f"odpt.Operator:{airline}",
                    "odpt:departureAirport": f"odpt.Airport:{origin}",
                },
            )
            for item in items:
                flight = normalize_flight(item, titles)
                if flight["to"] in dests:
                    out.append(flight)
    out.sort(key=lambda f: (f["from"], f["to"], f["scheduled"] or ""))
    return out


def fetch_trains(client: OdptClient, config: TransitConfig, titles: dict[str, str]) -> list[dict]:
    wanted = list(config.usable_railways)
    out = []
    for operator in sorted({railway_operator(r) for r in wanted}):
        public = operator in PUBLIC_OPERATORS
        items = client.get(
            "odpt:TrainInformation", {"odpt:operator": f"odpt.Operator:{operator}"}, public
        )
        by_railway = {i.get("odpt:railway"): i for i in items}
        for railway in wanted:
            if railway_operator(railway) == operator and railway in by_railway:
                out.append(normalize_train(by_railway[railway], titles))
    out.sort(key=lambda t: wanted.index(t["railway"]))
    return out


def fetch_titles(
    client: OdptClient, config: TransitConfig
) -> tuple[dict[str, str], dict[str, str]]:
    """運航状況の日本語名と、路線名を取る（起動時に 1 回）。"""
    status_titles: dict[str, str] = {}
    if config.flight_routes and config.odpt_token:
        for s in client.get("odpt:FlightStatus", {}):
            status_titles[s.get("owl:sameAs")] = _ja(s.get("odpt:flightStatusTitle")) or ""
    railway_titles: dict[str, str] = {}
    for operator in sorted({railway_operator(r) for r in config.usable_railways}):
        public = operator in PUBLIC_OPERATORS
        for r in client.get("odpt:Railway", {"odpt:operator": f"odpt.Operator:{operator}"}, public):
            railway_titles[r.get("owl:sameAs")] = _ja(r.get("odpt:railwayTitle")) or r.get(
                "dc:title", ""
            )
    return status_titles, railway_titles


class TransitCache:
    """interval_s ごとに ODPT から取り直して、最新の値を持っておく。"""

    def __init__(self, config: TransitConfig, client: OdptClient | None = None) -> None:
        self.config = config
        self.client = client or OdptClient(config.odpt_token)
        self._lock = threading.Lock()
        self._snapshot = TransitSnapshot()
        self._titles: tuple[dict[str, str], dict[str, str]] | None = None
        self._stop = threading.Event()

    def snapshot(self) -> TransitSnapshot:
        with self._lock:
            return self._snapshot

    def refresh(self) -> None:
        try:
            if self._titles is None:
                self._titles = fetch_titles(self.client, self.config)
            status_titles, railway_titles = self._titles
            flights = (
                fetch_flights(self.client, self.config, status_titles)
                if self.config.flight_routes and self.config.odpt_token
                else []
            )
            trains = fetch_trains(self.client, self.config, railway_titles)
            snap = TransitSnapshot(flights, trains, time.time(), None)
        except Exception as e:  # 取れなかったときは前の値を残し、エラーだけ記録する
            log.warning("運行状況を取れませんでした: %s", e)
            old = self.snapshot()
            snap = TransitSnapshot(old.flights, old.trains, old.fetched_at, str(e))
        with self._lock:
            self._snapshot = snap

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self.config.interval_s)

        threading.Thread(target=loop, name="transit", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def sources(config: TransitConfig) -> list[str]:
    """画面に出す出典の事業者名。"""
    ops = list(config.airlines) if config.flight_routes and config.odpt_token else []
    ops += [railway_operator(r) for r in config.usable_railways]  # 設定に書いた順
    return [OPERATOR_NAMES.get(o, o) for o in dict.fromkeys(ops)]
