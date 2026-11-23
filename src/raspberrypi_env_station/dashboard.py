"""大型モニター用ダッシュボードの Web サーバー。

SQLite の計測値を JSON で返し、web/build（SvelteKit でビルドした静的ファイル）を配信する。
Pi 自身の Chromium から開く前提で、既定では 127.0.0.1 だけで待ち受ける。

uv run env-dashboard --config config.toml
"""

import argparse
import json
import logging
import mimetypes
import sqlite3
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from raspberrypi_env_station.config import Config, load_config
from raspberrypi_env_station.transit import AIRPORTS, TransitCache, sources

log = logging.getLogger("raspberrypi_env_station.dashboard")

SENSOR = "scd4x"
METRICS = ("co2_ppm", "temperature_c", "humidity_pct")
MAX_HOURS = 24 * 7
MAX_POINTS = 720  # グラフの点の上限。超えたら時間で区切って平均する

# Windows のレジストリなど環境によって .js の型が変わらないよう固定する
for _ext, _type in {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.items():
    mimetypes.add_type(_type, _ext)


def connect_readonly(path: Path) -> sqlite3.Connection | None:
    """計測側（env-station）が書いている DB を読み取り専用で開く。まだ無ければ None。"""
    if not path.exists():
        return None
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def station(config: Config, conn: sqlite3.Connection | None) -> dict[str, Any] | None:
    if (st := config.station) is not None:
        return {"name": st.name, "latitude": st.latitude, "longitude": st.longitude}
    if conn is None:
        return None
    row = conn.execute("SELECT name, latitude, longitude FROM station").fetchone()
    return None if row is None else {"name": row[0], "latitude": row[1], "longitude": row[2]}


def offices(config: Config, st: dict[str, Any] | None) -> list[dict[str, Any]]:
    """地図に並べる拠点。設定が無ければ設置場所を 1 つだけ出す。"""
    if config.dashboard.offices:
        return [
            {
                "name": o.name,
                "label": o.label,
                "latitude": o.latitude,
                "longitude": o.longitude,
                "zoom": o.zoom,
            }
            for o in config.dashboard.offices
        ]
    if st is None:
        return []
    return [{**st, "label": "", "zoom": 12}]


def latest(conn: sqlite3.Connection | None) -> dict[str, Any]:
    """指標ごとの最新値。値が無い指標は None。"""
    result: dict[str, Any] = {"ts": None, **dict.fromkeys(METRICS)}
    if conn is None:
        return result
    for metric in METRICS:
        row = conn.execute(
            "SELECT ts, value FROM readings WHERE sensor = ? AND metric = ? "
            "ORDER BY ts DESC LIMIT 1",
            (SENSOR, metric),
        ).fetchone()
        if row is not None:
            result[metric] = row[1]
            result["ts"] = max(result["ts"] or row[0], row[0])
    return result


def downsample(points: list[tuple[str, float]], max_points: int) -> list[tuple[str, float]]:
    """点が多すぎるときは、順に max_points 個のまとまりに分けて平均する（時刻は先頭の値）。"""
    if len(points) <= max_points:
        return points
    size = -(-len(points) // max_points)  # 切り上げ
    out = []
    for i in range(0, len(points), size):
        chunk = points[i : i + size]
        out.append((chunk[0][0], round(sum(v for _, v in chunk) / len(chunk), 2)))
    return out


def series(
    conn: sqlite3.Connection | None, metric: str, hours: float, now: datetime | None = None
) -> list[tuple[str, float]]:
    if conn is None:
        return []
    since = (now or datetime.now(UTC)) - timedelta(hours=hours)
    rows = conn.execute(
        "SELECT ts, value FROM readings WHERE sensor = ? AND metric = ? AND ts >= ? ORDER BY ts",
        (SENSOR, metric, since.isoformat()),
    ).fetchall()
    return downsample(rows, MAX_POINTS)


def transit_body(config: Config, cache: TransitCache | None) -> dict[str, Any]:
    """運行状況。設定が無ければ enabled: false。ODPT の規約で画面に出す出典・問い合わせ先も返す。"""
    tc = config.transit
    if cache is None or not tc.enabled:
        return {"enabled": False}
    snap = cache.snapshot()
    fetched = datetime.fromtimestamp(snap.fetched_at, UTC).isoformat() if snap.fetched_at else None
    return {
        "enabled": True,
        "flights": snap.flights,
        "trains": snap.trains,
        "fetched_at": fetched,
        "error": snap.error,
        "sources": sources(tc),
        "contact": tc.contact,
        "airports": AIRPORTS,
        "routes": [list(r) for r in tc.flight_routes],
    }


class DashboardHandler(BaseHTTPRequestHandler):
    config: Config
    web_dir: Path
    transit: TransitCache | None = None

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path.startswith("/api/"):
            self._api(url.path, parse_qs(url.query))
        else:
            self._static(url.path)

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        conn = connect_readonly(self.config.database)
        try:
            match path:
                case "/api/config":
                    st = station(self.config, conn)
                    body: Any = {"station": st, "offices": offices(self.config, st)}
                case "/api/latest":
                    body = latest(conn)
                case "/api/transit":
                    body = transit_body(self.config, self.transit)
                case "/api/series":
                    metric = query.get("metric", [""])[0]
                    if metric not in METRICS:
                        return self._error(HTTPStatus.BAD_REQUEST, f"metric は {METRICS} のどれか")
                    try:
                        hours = float(query.get("hours", ["24"])[0])
                    except ValueError:
                        return self._error(HTTPStatus.BAD_REQUEST, "hours は数値")
                    if not 0 < hours <= MAX_HOURS:
                        return self._error(HTTPStatus.BAD_REQUEST, f"hours は 0〜{MAX_HOURS}")
                    body = {"metric": metric, "points": series(conn, metric, hours)}
                case _:
                    return self._error(HTTPStatus.NOT_FOUND, "not found")
        finally:
            if conn is not None:
                conn.close()
        self._send(HTTPStatus.OK, "application/json", json.dumps(body, ensure_ascii=False).encode())

    def _static(self, path: str) -> None:
        root = self.web_dir.resolve()
        if not root.is_dir():
            return self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                f"{self.web_dir} がありません。web で pnpm install && pnpm build を実行する",
            )
        target = (root / path.lstrip("/")).resolve()
        if not target.is_relative_to(root):
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            target = root / "index.html"  # 画面は 1 枚だけなので、知らないパスはトップを返す
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, ctype, target.read_bytes())

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._send(status, "application/json", json.dumps({"error": message}).encode())

    def _send(self, status: HTTPStatus, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        log.debug(format, *args)


def make_server(
    config: Config,
    web_dir: Path,
    host: str,
    port: int,
    transit: TransitCache | None = None,
) -> ThreadingHTTPServer:
    attrs = {"config": config, "web_dir": web_dir, "transit": transit}
    handler = type("Handler", (DashboardHandler,), attrs)
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="大型モニター用ダッシュボードを配信する")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--web-dir", default="web/build", type=Path)
    parser.add_argument("--host", help="既定は config.toml の [dashboard] host（127.0.0.1）")
    parser.add_argument("--port", type=int)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config(args.config)
    host = args.host or config.dashboard.host
    port = args.port or config.dashboard.port
    transit = None
    if config.transit.enabled:
        transit = TransitCache(config.transit)
        transit.start()  # interval_s ごとに ODPT から取り直す
    server = make_server(config, args.web_dir, host, port, transit)
    log.info("http://%s:%d/ で配信中（Ctrl+C で終了）", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if transit is not None:
            transit.stop()
        server.server_close()


if __name__ == "__main__":
    main()
