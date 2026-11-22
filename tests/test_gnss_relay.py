import socket

import pytest

from raspberrypi_env_station import gnss_relay
from raspberrypi_env_station.gnss_relay import (
    READ_CHUNK,
    WRITE_CHUNK,
    Relay,
    drain,
    parse_available,
    split_writes,
)

# UBX-CFG-VALSET の例（qzss_dcr が送るものと同じ形。中身は問わない）
UBX_FRAME = bytes.fromhex("b562068a0900000100000014003110017f8b")


class FakePort:
    """受信機の代わり。output に入れたバイト列を I2C から読める。"""

    def __init__(self, output: bytes = b"") -> None:
        self.output = output
        self.written: list[bytes] = []
        self.reads: list[int] = []
        self.fail = 0  # この回数だけ OSError を起こす
        self.closed = False

    def available(self) -> int:
        if self.fail:
            self.fail -= 1
            raise OSError(121, "Remote I/O error")
        return len(self.output)

    def read(self, n: int) -> bytes:
        self.reads.append(n)
        data, self.output = self.output[:n], self.output[n:]
        return data

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setattr(gnss_relay.time, "sleep", lambda _s: None)
    r = Relay(FakePort(), "127.0.0.1", 0, interval_s=0.01)
    yield r
    r.close()


def connect(relay: Relay) -> socket.socket:
    client = socket.create_connection(relay.address[:2], timeout=2)
    relay.step()  # 接続を受け付ける
    assert len(relay.clients) == 1
    return client


def step_until(relay: Relay, condition, steps: int = 50) -> None:
    for _ in range(steps):
        relay.step()
        if condition():
            return
    raise AssertionError("条件を満たさなかった")


def test_parse_available_is_big_endian():
    assert parse_available(bytes([0x01, 0x02])) == 0x0102


def test_parse_available_ignores_top_bit():
    assert parse_available(bytes([0x80, 0x10])) == 0x10


def test_drain_reads_everything_in_chunks():
    port = FakePort(bytes(range(256)) * 3)
    assert drain(port) == bytes(range(256)) * 3
    assert port.reads == [READ_CHUNK, READ_CHUNK, READ_CHUNK, 768 - 3 * READ_CHUNK]


def test_drain_does_not_read_when_empty():
    port = FakePort()
    assert drain(port) == b""
    assert port.reads == []


@pytest.mark.parametrize("length", [2, 3, WRITE_CHUNK, WRITE_CHUNK + 1, WRITE_CHUNK + 2, 1000])
def test_split_writes_never_sends_a_single_byte(length):
    data = bytes(i % 256 for i in range(length))
    chunks, rest = split_writes(data)
    assert rest == b""
    assert b"".join(chunks) == data
    assert all(2 <= len(c) <= WRITE_CHUNK for c in chunks)


def test_split_writes_holds_a_lone_byte():
    assert split_writes(b"\xb5") == ([], b"\xb5")


def test_receiver_output_goes_to_client(relay):
    client = connect(relay)
    relay.port.output = UBX_FRAME
    relay.step()
    assert client.recv(1024) == UBX_FRAME


def test_client_bytes_go_to_receiver_unchanged(relay):
    client = connect(relay)
    client.sendall(UBX_FRAME)
    step_until(relay, lambda: b"".join(relay.port.written) == UBX_FRAME)


def test_lone_byte_waits_for_the_next(relay):
    client = connect(relay)
    client.sendall(UBX_FRAME[:1])
    for _ in range(5):
        relay.step()
    assert relay.port.written == []
    client.sendall(UBX_FRAME[1:])
    step_until(relay, lambda: b"".join(relay.port.written) == UBX_FRAME)
    assert all(len(c) >= 2 for c in relay.port.written)


def test_i2c_failure_keeps_client_connected(relay):
    client = connect(relay)
    relay.port.fail = 3
    for _ in range(3):
        relay.step()
    assert not relay.port_ok
    assert len(relay.clients) == 1
    relay.port.output = b"after"
    relay.step()
    assert relay.port_ok
    assert client.recv(1024) == b"after"


def test_disconnect_is_cleaned_up(relay):
    client = connect(relay)
    client.close()
    step_until(relay, lambda: not relay.clients)


def test_output_is_drained_without_clients(relay):
    # 読まないと受信機が出力を止めるので、クライアントがいなくても読み続ける
    relay.port.output = b"x" * 10
    relay.step()
    assert relay.port.output == b""


def test_close_closes_the_port(relay):
    relay.close()
    assert relay.port.closed
