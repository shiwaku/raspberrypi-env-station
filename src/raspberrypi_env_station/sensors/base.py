from typing import Protocol

# 1 回の計測結果。キーは指標名（例: "temperature_c"）、値は数値。
# 値が取れなかった指標はキーごと省く。
type Reading = dict[str, float]


class Sensor(Protocol):
    name: str

    def read(self) -> Reading: ...

    def close(self) -> None: ...
