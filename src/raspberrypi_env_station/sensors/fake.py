"""実機なしで動作確認するためのダミーセンサー。"""

import math
import random
import time

from raspberrypi_env_station.sensors.base import Reading


class FakeSensor:
    def __init__(self, name: str, seed: int | None = None) -> None:
        self.name = name
        self._rng = random.Random(seed)

    def read(self) -> Reading:
        # 1 日周期の緩やかな変化 + ノイズ
        phase = math.sin(time.time() / 86400 * 2 * math.pi)
        noise = self._rng.gauss
        match self.name:
            case "scd4x":
                return {
                    "co2_ppm": float(round(600 + 200 * phase + noise(0, 20))),
                    "temperature_c": round(21 + 5 * phase + noise(0, 0.2), 2),
                    "humidity_pct": round(48 - 10 * phase + noise(0, 1), 2),
                }
            case _:
                return {"value": round(noise(0, 1), 3)}

    def close(self) -> None:
        pass
