"""Sensirion SCD40 / SCD41（CO2・温度・湿度）。I2C 接続。

秋月 AE-SCD40-BO（SCD40 搭載）で使う想定。SCD40 の CO2 保証範囲は 400〜2000 ppm。

データシートのコマンドを smbus2 で直接送る。周期計測モードでは 5 秒ごとに新しい値が出る。
"""

import time

from raspberrypi_env_station.sensors.base import Reading

_START_PERIODIC = 0x21B1
_STOP_PERIODIC = 0x3F86
_READ_MEASUREMENT = 0xEC05
_GET_DATA_READY = 0xE4B8


def crc8(data: bytes) -> int:
    """Sensirion の CRC-8（多項式 0x31、初期値 0xFF）。"""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def parse_words(raw: bytes) -> list[int]:
    """[MSB, LSB, CRC] × n の応答を検証して 16bit 値の列にする。"""
    if len(raw) % 3 != 0:
        raise ValueError(f"応答長が 3 の倍数ではない: {len(raw)}")
    words = []
    for i in range(0, len(raw), 3):
        chunk = raw[i : i + 2]
        if crc8(chunk) != raw[i + 2]:
            raise ValueError(f"CRC 不一致（{i // 3} 語目）")
        words.append(int.from_bytes(chunk, "big"))
    return words


def convert_measurement(words: list[int]) -> Reading:
    co2, t_raw, rh_raw = words
    return {
        "co2_ppm": float(co2),
        "temperature_c": round(-45 + 175 * t_raw / 65535, 2),
        "humidity_pct": round(100 * rh_raw / 65535, 2),
    }


class SCD4x:
    name = "scd4x"

    def __init__(self, bus: int = 1, address: int = 0x62) -> None:
        import smbus2

        self._smbus2 = smbus2
        self._bus = smbus2.SMBus(bus)
        self._address = address
        self._send(_STOP_PERIODIC)  # 前回の計測が残っていても初期化できるように
        time.sleep(0.5)
        self._send(_START_PERIODIC)

    def _send(self, command: int) -> None:
        msg = self._smbus2.i2c_msg.write(self._address, command.to_bytes(2, "big"))
        self._bus.i2c_rdwr(msg)

    def _query(self, command: int, n_words: int) -> list[int]:
        self._send(command)
        time.sleep(0.001)
        msg = self._smbus2.i2c_msg.read(self._address, n_words * 3)
        self._bus.i2c_rdwr(msg)
        return parse_words(bytes(msg))

    def _data_ready(self) -> bool:
        (status,) = self._query(_GET_DATA_READY, 1)
        return status & 0x07FF != 0

    def read(self) -> Reading:
        deadline = time.monotonic() + 6
        while not self._data_ready():
            if time.monotonic() > deadline:
                return {}
            time.sleep(0.5)
        return convert_measurement(self._query(_READ_MEASUREMENT, 3))

    def close(self) -> None:
        try:
            self._send(_STOP_PERIODIC)
        finally:
            self._bus.close()
