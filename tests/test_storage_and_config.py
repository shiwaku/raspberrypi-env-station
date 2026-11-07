from datetime import UTC, datetime, timedelta

import pytest

from raspberrypi_env_station.cli import collect_once
from raspberrypi_env_station.config import parse_config
from raspberrypi_env_station.sensors.fake import FakeSensor
from raspberrypi_env_station.storage import Storage


def test_storage_roundtrip():
    storage = Storage(":memory:")
    t0 = datetime(2026, 11, 7, tzinfo=UTC)
    storage.write(t0, "scd4x", {"co2_ppm": 600.0, "temperature_c": 21.5})
    storage.write(t0 + timedelta(minutes=1), "scd4x", {"co2_ppm": 650.0})

    assert storage.series("scd4x", "co2_ppm") == [
        (t0.isoformat(), 600.0),
        ((t0 + timedelta(minutes=1)).isoformat(), 650.0),
    ]
    assert len(storage.series("scd4x", "co2_ppm", since=t0 + timedelta(seconds=30))) == 1


class BrokenSensor:
    name = "broken"

    def read(self):
        raise OSError("I2C error")

    def close(self):
        pass


def test_collect_once_continues_after_failure():
    storage = Storage(":memory:")
    written = collect_once([BrokenSensor(), FakeSensor("scd4x", seed=0)], storage)
    assert written == 3
    assert len(storage.series("scd4x", "co2_ppm")) == 1


def test_parse_config_skips_disabled_and_keeps_options():
    config = parse_config(
        {
            "interval_s": 30,
            "sensors": [
                {"type": "scd4x", "address": 0x62},
                {"type": "scd4x", "address": 0x63, "enabled": False},
            ],
        }
    )
    assert config.interval_s == 30
    assert len(config.sensors) == 1
    assert config.sensors[0].options == {"address": 0x62}
    assert config.station is None


def test_parse_config_station():
    config = parse_config({"station": {"name": "オフィス", "latitude": 43.06, "longitude": 141.35}})
    assert config.station is not None
    assert (config.station.latitude, config.station.longitude) == (43.06, 141.35)


def test_parse_config_rejects_out_of_range_station():
    with pytest.raises(ValueError, match="範囲外"):
        parse_config({"station": {"latitude": 141.35, "longitude": 43.06 + 200}})


def test_storage_station_is_single_row():
    storage = Storage(":memory:")
    storage.set_station("旧", 1.0, 2.0)
    storage.set_station("オフィス", 43.06, 141.35)
    assert storage.station() == ("オフィス", 43.06, 141.35)


def test_parse_config_rejects_unknown_type():
    with pytest.raises(ValueError, match="未対応"):
        parse_config({"sensors": [{"type": "gps"}]})


def test_parse_config_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        parse_config({"interval_s": 0})
