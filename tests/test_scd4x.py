import pytest

from raspberrypi_env_station.sensors.scd4x import convert_measurement, crc8, parse_words


def test_crc8_matches_datasheet_example():
    # Sensirion データシートの例: 0xBEEF -> CRC 0x92
    assert crc8(bytes([0xBE, 0xEF])) == 0x92


def test_parse_words_validates_crc():
    raw = bytes([0xBE, 0xEF, 0x92, 0x01, 0xF4, crc8(bytes([0x01, 0xF4]))])
    assert parse_words(raw) == [0xBEEF, 500]


def test_parse_words_rejects_bad_crc():
    with pytest.raises(ValueError, match="CRC"):
        parse_words(bytes([0xBE, 0xEF, 0x00]))


def test_parse_words_rejects_bad_length():
    with pytest.raises(ValueError):
        parse_words(bytes([0xBE, 0xEF]))


def test_convert_measurement():
    # データシートの変換式: T = -45 + 175 * raw / 65535, RH = 100 * raw / 65535
    reading = convert_measurement([850, 0x6667, 0x5EB9])
    assert reading["co2_ppm"] == 850
    assert reading["temperature_c"] == pytest.approx(25.0, abs=0.01)
    assert reading["humidity_pct"] == pytest.approx(37.0, abs=0.01)
