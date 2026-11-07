"""定期計測ループ。

uv run env-station --config config.toml          # 実機
uv run env-station --config config.toml --fake   # ダミーセンサーで動作確認
"""

import argparse
import logging
import signal
import time
from datetime import UTC, datetime

from raspberrypi_env_station.config import Config, SensorConfig, load_config
from raspberrypi_env_station.sensors.base import Sensor
from raspberrypi_env_station.sensors.fake import FakeSensor
from raspberrypi_env_station.storage import Storage

log = logging.getLogger("raspberrypi_env_station")


def build_sensor(cfg: SensorConfig, fake: bool) -> Sensor:
    if fake:
        return FakeSensor(cfg.type)
    match cfg.type:
        case "scd4x":
            from raspberrypi_env_station.sensors.scd4x import SCD4x

            return SCD4x(**cfg.options)
    raise ValueError(cfg.type)


def collect_once(sensors: list[Sensor], storage: Storage) -> int:
    """全センサーを 1 回ずつ読んで保存する。1 台の失敗で他を止めない。"""
    ts = datetime.now(UTC)
    total = 0
    for sensor in sensors:
        try:
            reading = sensor.read()
        except Exception:
            log.exception("%s の読み取りに失敗", sensor.name)
            continue
        if not reading:
            log.warning("%s: 値なし（データ未準備など）", sensor.name)
            continue
        total += storage.write(ts, sensor.name, reading)
        log.info("%s: %s", sensor.name, reading)
    return total


def run(config: Config, fake: bool, once: bool) -> None:
    sensors = [build_sensor(s, fake) for s in config.sensors]
    storage = Storage(config.database)
    if (st := config.station) is not None:
        storage.set_station(st.name, st.latitude, st.longitude)
    stop = False

    def handle_stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    try:
        while not stop:
            started = time.monotonic()
            collect_once(sensors, storage)
            if once:
                break
            # 計測にかかった時間を差し引いて周期を保つ
            remaining = config.interval_s - (time.monotonic() - started)
            while remaining > 0 and not stop:
                time.sleep(min(remaining, 0.5))
                remaining -= 0.5
    finally:
        for sensor in sensors:
            sensor.close()
        storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="センサー値を定期的に SQLite に記録する")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--fake", action="store_true", help="ダミーセンサーを使う")
    parser.add_argument("--once", action="store_true", help="1 回だけ計測して終了")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    run(load_config(args.config), fake=args.fake, once=args.once)


if __name__ == "__main__":
    main()
