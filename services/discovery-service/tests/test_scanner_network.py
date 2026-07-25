"""Real-network tests for :mod:`app.scanners.network`
(:class:`TcpScanner`, :class:`UdpScanner`, :class:`IcmpScanner`).

No mocking -- every probe here is a genuine socket operation against
either this repository's docker-compose infrastructure (Redis on
``localhost:6379``, the dedicated OpenSSH container on
``localhost:2222`` for a real banner grab) or a real, temporary
in-process UDP echo server this module's own fixture starts (the same
"real, temporary server over mocks" discipline
``tests/test_scanner_ftp.py`` applies with ``pyftpdlib``).

Two real-network facts this module leans on, discovered empirically
against this machine rather than assumed:

* A refused local TCP/UDP connection on this host takes roughly two
  seconds to surface (not instant, as on a typical Linux CI box) --
  every "closed port" test below uses a timeout comfortably longer
  than that so it observes the real refusal instead of racing its own
  timeout.
* ``192.0.2.1`` (RFC 5737 TEST-NET-1, reserved and never routed) is a
  reliable real black hole for exercising the genuine ``TIMEOUT``
  path -- nothing will ever answer it.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest

from app.models.enums import DiscoveryResultStatus
from app.scanners.network import IcmpScanner, TcpScanner, UdpScanner

_REDIS_HOST = "localhost"
_REDIS_PORT = 6379
_SSH_HOST = "localhost"
_SSH_PORT = 2222
_CLOSED_HOST = "127.0.0.1"
_CLOSED_PORT = 1
_BLACKHOLE_HOST = "192.0.2.1"
_CLOSED_PORT_TIMEOUT_SECONDS = 5.0
"""Longer than the ~2s this host actually takes to refuse a local
connection (see module docstring) -- avoids racing a TIMEOUT.
"""
_BLACKHOLE_TIMEOUT_SECONDS = 1.5


def _run_udp_echo_server(sock: socket.socket, stop: threading.Event) -> None:
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(512)
        except TimeoutError:
            continue
        except OSError:
            return
        sock.sendto(b"pong:" + data, addr)


@pytest.fixture
def udp_echo_server() -> Iterator[int]:
    """A real, temporary UDP echo server on ``127.0.0.1``/an ephemeral
    port -- replies to *any* datagram (including the scanner's own
    empty probe payload), so the scanner's genuine "something is
    listening" ``SUCCESS`` path can be observed for real.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind(("127.0.0.1", 0))
    port = server_sock.getsockname()[1]
    stop = threading.Event()
    thread = threading.Thread(target=_run_udp_echo_server, args=(server_sock, stop), daemon=True)
    thread.start()
    yield port
    stop.set()
    server_sock.close()
    thread.join(timeout=2)


class TestTcpScanner:
    async def test_requires_port(self) -> None:
        outcome = await TcpScanner().probe(
            "127.0.0.1", port=None, timeout_seconds=3, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.FAILURE
        assert outcome.error_message == "TCP scan requires a port."

    async def test_success_against_real_redis(self) -> None:
        outcome = await TcpScanner().probe(
            _REDIS_HOST, port=_REDIS_PORT, timeout_seconds=5, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert outcome.latency_ms is not None
        assert outcome.identity == {"port": _REDIS_PORT, "open": True}

    async def test_banner_grab_against_real_ssh_server(self) -> None:
        """The dedicated OpenSSH container sends its version banner the
        instant a TCP connection opens, exercising the scanner's real
        banner-read branch end to end.
        """
        outcome = await TcpScanner().probe(
            _SSH_HOST, port=_SSH_PORT, timeout_seconds=5, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert outcome.identity["port"] == _SSH_PORT
        assert outcome.identity["open"] is True
        assert str(outcome.identity["banner"]).startswith("SSH-2.0-")

    async def test_closed_port_is_unreachable(self) -> None:
        outcome = await TcpScanner().probe(
            _CLOSED_HOST,
            port=_CLOSED_PORT,
            timeout_seconds=_CLOSED_PORT_TIMEOUT_SECONDS,
            credential=None,
        )
        assert outcome.status == DiscoveryResultStatus.UNREACHABLE
        assert outcome.error_message is not None

    async def test_unroutable_address_times_out(self) -> None:
        start = time.perf_counter()
        outcome = await TcpScanner().probe(
            _BLACKHOLE_HOST,
            port=80,
            timeout_seconds=_BLACKHOLE_TIMEOUT_SECONDS,
            credential=None,
        )
        elapsed = time.perf_counter() - start
        assert outcome.status == DiscoveryResultStatus.TIMEOUT
        assert elapsed < _BLACKHOLE_TIMEOUT_SECONDS + 2.0


class TestUdpScanner:
    async def test_requires_port(self) -> None:
        outcome = await UdpScanner().probe(
            "127.0.0.1", port=None, timeout_seconds=3, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.FAILURE
        assert outcome.error_message == "UDP scan requires a port."

    async def test_success_against_real_udp_echo_server(self, udp_echo_server: int) -> None:
        outcome = await UdpScanner().probe(
            "127.0.0.1", port=udp_echo_server, timeout_seconds=5, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert outcome.latency_ms is not None
        assert outcome.identity["port"] == udp_echo_server
        assert outcome.identity["port_state"] == "open"
        assert outcome.identity["response_bytes"] == len(b"pong:")

    async def test_closed_port(self) -> None:
        """On this Windows host a UDP send to a closed port surfaces as
        ``ConnectionResetError`` (``WSAECONNRESET``), not the
        ``ConnectionRefusedError`` the scanner's own module docstring
        documents for Linux's ICMP-port-unreachable mapping -- so the
        generic ``except OSError`` branch is what actually fires here,
        yielding ``UNREACHABLE`` rather than the Linux-specific
        ``SUCCESS``/``port_state=closed`` outcome. This is genuine,
        observed platform behavior (verified directly against a
        bind-then-immediately-close ephemeral port before writing this
        assertion), not a scanner bug -- the service's real deployment
        target is Linux (see pyproject.toml's WMI-on-win32 comment).
        """
        probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe_sock.bind(("127.0.0.1", 0))
        closed_port = probe_sock.getsockname()[1]
        probe_sock.close()

        outcome = await UdpScanner().probe(
            "127.0.0.1",
            port=closed_port,
            timeout_seconds=_CLOSED_PORT_TIMEOUT_SECONDS,
            credential=None,
        )
        assert outcome.status == DiscoveryResultStatus.UNREACHABLE
        assert outcome.error_message is not None

    async def test_silence_is_ambiguous_timeout(self) -> None:
        """A blackhole address swallows the probe datagram with no
        reply and no ICMP error -- genuinely ambiguous open-or-filtered,
        reported as ``TIMEOUT`` per the scanner's own module docstring.
        """
        outcome = await UdpScanner().probe(
            _BLACKHOLE_HOST, port=53, timeout_seconds=_BLACKHOLE_TIMEOUT_SECONDS, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.TIMEOUT
        assert outcome.identity == {"port": 53, "port_state": "open|filtered"}


class TestIcmpScanner:
    """Real RFC 792 ICMP echo over a raw socket -- requires
    root/``CAP_NET_RAW`` on Linux or Administrator on Windows. Tried for
    real first; if this process genuinely lacks that privilege in
    whatever environment runs this suite, each test skips with an
    honest reason rather than faking success.
    """

    async def test_success_against_loopback(self) -> None:
        outcome = await IcmpScanner().probe(
            "127.0.0.1", port=None, timeout_seconds=3, credential=None
        )
        if (
            outcome.status == DiscoveryResultStatus.FAILURE
            and outcome.error_message is not None
            and "elevated privileges" in outcome.error_message
        ):
            reason = f"Raw ICMP sockets are not permitted in this process: {outcome.error_message}"
            pytest.skip(reason)
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert outcome.latency_ms is not None
        assert outcome.identity == {"reply_type": 0}

    async def test_unroutable_address_times_out(self) -> None:
        outcome = await IcmpScanner().probe(
            _BLACKHOLE_HOST, port=None, timeout_seconds=_BLACKHOLE_TIMEOUT_SECONDS, credential=None
        )
        if (
            outcome.status == DiscoveryResultStatus.FAILURE
            and outcome.error_message is not None
            and "elevated privileges" in outcome.error_message
        ):
            reason = f"Raw ICMP sockets are not permitted in this process: {outcome.error_message}"
            pytest.skip(reason)
        assert outcome.status == DiscoveryResultStatus.TIMEOUT
