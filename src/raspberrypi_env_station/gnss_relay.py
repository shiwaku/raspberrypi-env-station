"""MAX-M10S（u-blox M10）の I2C と TCP をつなぐ中継プログラム。

qzss_dcr は I2C を直接読めないので、受信機が I2C に出すバイト列を TCP（既定 127.0.0.1:2101）に流し、
TCP で受けたバイト列（qzss_dcr が送る L1S の設定など）を I2C で受信機に書き込む。中身は加工しない。

uv run gnss-relay                      # 実機（I2C バス 1、アドレス 0x42）
python3 qzss_dcr.py --tcp localhost:2101 --configure-m10 --ubx-port I2C

I2C の決まり（MAX-M10S Integration manual UBX-20053088 の 2.2.2）:
- 0xFD・0xFE に読める残りのバイト数（0xFD が上位）。0xFF からデータが続けて読める
- 1.5 秒読まないと受信機は出力を止める。受信機側のバッファは 4KB
- 書き込みは UBX・NMEA をそのまま送る。1 回に 2 バイト以上（1 バイトはレジスタの指定とみなされる）
"""

import argparse
import logging
import selectors
import signal
import socket
import time
from typing import Protocol

log = logging.getLogger("raspberrypi_env_station.gnss_relay")

REG_BYTES_AVAILABLE = 0xFD
READ_CHUNK = 255  # 1 回の I2C 読み取りの上限
WRITE_CHUNK = 255  # 1 回の I2C 書き込みの上限
SEND_TIMEOUT_S = 1.0  # TCP クライアントが詰まったときに切るまでの時間


class Port(Protocol):
    """受信機との I2C のやりとり。テストでは偽物に差し替える。"""

    def available(self) -> int: ...
    def read(self, n: int) -> bytes: ...
    def write(self, data: bytes) -> None: ...
    def close(self) -> None: ...


class UbloxI2C:
    """smbus2 で u-blox の I2C（DDC）を読み書きする。"""

    def __init__(self, bus: int = 1, address: int = 0x42) -> None:
        import smbus2

        self._smbus2 = smbus2
        self._bus = smbus2.SMBus(bus)
        self._address = address

    def available(self) -> int:
        """読める残りのバイト数。

        読んだあと受信機のアドレスは 0xFF（データ）を指したままになるので、続けて read() で読める。
        """
        write = self._smbus2.i2c_msg.write(self._address, [REG_BYTES_AVAILABLE])
        read = self._smbus2.i2c_msg.read(self._address, 2)
        self._bus.i2c_rdwr(write, read)
        return parse_available(bytes(read))

    def read(self, n: int) -> bytes:
        msg = self._smbus2.i2c_msg.read(self._address, n)
        self._bus.i2c_rdwr(msg)
        return bytes(msg)

    def write(self, data: bytes) -> None:
        msg = self._smbus2.i2c_msg.write(self._address, data)
        self._bus.i2c_rdwr(msg)

    def close(self) -> None:
        self._bus.close()


def parse_available(raw: bytes) -> int:
    """0xFD・0xFE の 2 バイトをバイト数にする。

    最上位ビットが立つことがあると SparkFun のライブラリが報告している。受信機のバッファは
    4KB なので本来は立たないため、落として使う。
    """
    return int.from_bytes(raw, "big") & 0x7FFF


def drain(port: Port) -> bytes:
    """受信機が出したバイト列をすべて読む。"""
    n = port.available()
    chunks = []
    while n > 0:
        size = min(n, READ_CHUNK)
        chunks.append(port.read(size))
        n -= size
    return b"".join(chunks)


def split_writes(pending: bytes) -> tuple[list[bytes], bytes]:
    """書き込むバイト列を 2 バイト以上・WRITE_CHUNK 以下に分ける。

    1 バイトだけ残るときは次に届くバイトと合わせて送るため、返す。
    """
    chunks = []
    i = 0
    while len(pending) - i >= 2:
        size = min(WRITE_CHUNK, len(pending) - i)
        if len(pending) - i - size == 1:  # 最後に 1 バイトだけ残らないように 1 バイト減らす
            size -= 1
        chunks.append(pending[i : i + size])
        i += size
    return chunks, pending[i:]


class Relay:
    """I2C の受信機と TCP クライアントのあいだでバイト列を中継する。"""

    def __init__(self, port: Port, host: str, tcp_port: int, interval_s: float) -> None:
        self.port = port
        self.interval_s = interval_s
        self.server = socket.create_server((host, tcp_port))
        self.server.setblocking(False)
        self.address = self.server.getsockname()
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.server, selectors.EVENT_READ)
        # クライアント -> I2C にまだ書いていない 1 バイト
        self.clients: dict[socket.socket, bytes] = {}
        self.stopped = False
        self.port_ok = True  # I2C の失敗を 1 回だけ記録するため

    def serve(self) -> None:
        log.info("%s:%d で待ち受け中", *self.address[:2])
        try:
            while not self.stopped:
                self.step()
        finally:
            self.close()

    def step(self) -> None:
        """受信機から読んでクライアントへ送り、クライアントから届いたものを受信機へ書く。"""
        started = time.monotonic()
        try:
            data = drain(self.port)
        except OSError as e:
            self.port_failed(e)
            data = b""
        else:
            self.port_recovered()
        if data:
            self.broadcast(data)
        timeout = max(0.0, self.interval_s - (time.monotonic() - started))
        for key, _ in self.selector.select(timeout):
            if key.fileobj is self.server:
                self.accept()
            else:
                self.receive(key.fileobj)  # type: ignore[arg-type]

    def accept(self) -> None:
        conn, addr = self.server.accept()
        conn.setblocking(True)
        conn.settimeout(SEND_TIMEOUT_S)
        self.clients[conn] = b""
        self.selector.register(conn, selectors.EVENT_READ)
        log.info("接続: %s:%d", *addr[:2])

    def receive(self, conn: socket.socket) -> None:
        try:
            data = conn.recv(4096)
        except OSError:
            data = b""
        if not data:
            self.drop(conn)
            return
        chunks, rest = split_writes(self.clients[conn] + data)
        self.clients[conn] = rest
        try:
            for chunk in chunks:
                self.port.write(chunk)
        except OSError as e:
            self.port_failed(e)
            return
        log.debug("受信機へ %d バイト", len(data))

    def port_failed(self, error: OSError) -> None:
        """I2C の失敗（配線の抜き差しなど）。TCP はつないだまま、次の周期でやり直す。"""
        if self.port_ok:
            log.warning("I2C の読み書きに失敗: %s（つながるまでやり直す）", error)
            self.port_ok = False
        time.sleep(1)

    def port_recovered(self) -> None:
        if not self.port_ok:
            log.info("I2C が戻った")
            self.port_ok = True

    def broadcast(self, data: bytes) -> None:
        for conn in list(self.clients):
            try:
                conn.sendall(data)
            except OSError:
                log.warning("クライアントに送れないので切断する")
                self.drop(conn)

    def drop(self, conn: socket.socket) -> None:
        if conn not in self.clients:
            return
        self.selector.unregister(conn)
        del self.clients[conn]
        conn.close()
        log.info("切断")

    def close(self) -> None:
        for conn in list(self.clients):
            self.drop(conn)
        self.selector.close()
        self.server.close()
        self.port.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="MAX-M10S の I2C と TCP をつなぐ")
    parser.add_argument("--bus", type=int, default=1, help="I2C バス番号（既定 1）")
    parser.add_argument(
        "--address", type=lambda s: int(s, 0), default=0x42, help="受信機の I2C アドレス"
    )
    parser.add_argument("--host", default="127.0.0.1", help="待ち受けるアドレス")
    parser.add_argument("--port", type=int, default=2101, help="待ち受けるポート")
    parser.add_argument(
        "--interval", type=float, default=0.05, help="受信機を読む間隔（秒、1.5 未満）"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not 0 < args.interval < 1.5:
        parser.error("--interval は 0 より大きく 1.5 秒未満にする（受信機が出力を止めるため）")

    relay = Relay(UbloxI2C(args.bus, args.address), args.host, args.port, args.interval)

    def handle_stop(*_: object) -> None:
        relay.stopped = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    relay.serve()


if __name__ == "__main__":
    main()
