"""計測値を SQLite に縦持ち（1 行 = 時刻・センサー・指標・値）で保存する。"""

import sqlite3
from datetime import datetime
from pathlib import Path

from raspberrypi_env_station.sensors.base import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts     TEXT NOT NULL,  -- ISO 8601（UTC）
    sensor TEXT NOT NULL,
    metric TEXT NOT NULL,
    value  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_metric_ts ON readings (sensor, metric, ts);
CREATE TABLE IF NOT EXISTS station (
    id        INTEGER PRIMARY KEY CHECK (id = 1),  -- 設置場所は 1 か所
    name      TEXT NOT NULL,
    latitude  REAL NOT NULL,  -- WGS84
    longitude REAL NOT NULL
);
"""


class Storage:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def write(self, ts: datetime, sensor: str, reading: Reading) -> int:
        rows = [(ts.isoformat(), sensor, metric, value) for metric, value in reading.items()]
        with self._conn:
            self._conn.executemany("INSERT INTO readings VALUES (?, ?, ?, ?)", rows)
        return len(rows)

    def set_station(self, name: str, latitude: float, longitude: float) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO station VALUES (1, ?, ?, ?)", (name, latitude, longitude)
            )

    def station(self) -> tuple[str, float, float] | None:
        return self._conn.execute("SELECT name, latitude, longitude FROM station").fetchone()

    def series(
        self, sensor: str, metric: str, since: datetime | None = None
    ) -> list[tuple[str, float]]:
        query = "SELECT ts, value FROM readings WHERE sensor = ? AND metric = ?"
        params: list[str] = [sensor, metric]
        if since is not None:
            query += " AND ts >= ?"
            params.append(since.isoformat())
        return self._conn.execute(query + " ORDER BY ts", params).fetchall()

    def close(self) -> None:
        self._conn.close()
