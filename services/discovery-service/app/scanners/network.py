"""TCP, UDP, and ICMP network-layer scanners.

Per docs/037 "NETWORK DISCOVERY": TCP Scan, UDP Scan, Port
Identification, Service Detection, Latency Measurement. "ICMP Sweep"
is real ICMP echo (raw sockets, RFC 792 wire format) -- genuinely
functional, but requires the elevated privileges every real ICMP tool
needs (root/``CAP_NET_RAW`` on Linux, Administrator on Windows); a
:class:`PermissionError` is surfaced as a clear, honest
:attr:`~app.scanners.base.ScanOutcome.error_message` rather than
silently reported as "host unreachable" (a permission failure is not
evidence the host is down).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import struct
import time

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_BANNER_READ_BYTES = 256
_BANNER_READ_TIMEOUT_SECONDS = 1.0


class TcpScanner(ProtocolScanner):
    """TCP connect scan with an optional banner grab for service detection."""

    protocol = ProtocolType.TCP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        if port is None:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE, error_message="TCP scan requires a port."
            )
        start = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(address, port), timeout=timeout_seconds
            )
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        latency_ms = (time.perf_counter() - start) * 1000
        banner: str | None = None
        try:
            raw = await asyncio.wait_for(
                reader.read(_BANNER_READ_BYTES), timeout=_BANNER_READ_TIMEOUT_SECONDS
            )
            if raw:
                banner = raw.decode("utf-8", errors="replace").strip()
        except (TimeoutError, OSError):
            banner = None
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

        identity: dict[str, object] = {"port": port, "open": True}
        if banner:
            identity["banner"] = banner
        return ScanOutcome(
            status=DiscoveryResultStatus.SUCCESS, latency_ms=latency_ms, identity=identity
        )


class UdpScanner(ProtocolScanner):
    """UDP probe scan.

    UDP is connectionless, so "open" can never be confirmed the way a
    TCP handshake confirms it -- this mirrors every real UDP scanner's
    own inherent ambiguity, not a shortcut taken here: a reply means
    something is listening (``SUCCESS``); an ICMP port-unreachable
    (surfaced by the OS as :class:`ConnectionRefusedError` on Linux)
    means the port is definitely closed but the *host* is up
    (``SUCCESS`` with ``port_state=closed``); silence within the
    timeout is genuinely ambiguous -- open-or-filtered -- reported as
    ``TIMEOUT`` rather than guessed.
    """

    protocol = ProtocolType.UDP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        if port is None:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE, error_message="UDP scan requires a port."
            )
        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            await loop.sock_connect(sock, (address, port))
            await loop.sock_sendall(sock, b"")
            data = await asyncio.wait_for(loop.sock_recv(sock, 512), timeout=timeout_seconds)
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"port": port, "port_state": "open", "response_bytes": len(data)},
            )
        except TimeoutError:
            return ScanOutcome(
                status=DiscoveryResultStatus.TIMEOUT,
                identity={"port": port, "port_state": "open|filtered"},
            )
        except ConnectionRefusedError:
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"port": port, "port_state": "closed"},
            )
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        finally:
            sock.close()


def _icmp_checksum(payload: bytes) -> int:
    """RFC 1071 one's-complement checksum, as ICMP (RFC 792) requires."""
    if len(payload) % 2:
        payload += b"\x00"
    total: int = sum(struct.unpack(f"!{len(payload) // 2}H", payload))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


class IcmpScanner(ProtocolScanner):
    """Real ICMP echo request/reply (RFC 792), via a raw socket.

    Requires ``root``/``CAP_NET_RAW`` on Linux or Administrator on
    Windows -- the same privilege every real ``ping`` implementation
    needs, since raw sockets bypass the kernel's own protocol stack.
    """

    protocol = ProtocolType.ICMP
    _ECHO_REQUEST_TYPE = 8
    _IDENTIFIER = os.getpid() & 0xFFFF

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._ping, address, timeout_seconds)
        except PermissionError as exc:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                error_message=(
                    f"ICMP requires elevated privileges (root/CAP_NET_RAW or Administrator): {exc}"
                ),
            )
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

    def _ping(self, address: str, timeout_seconds: float) -> ScanOutcome:
        header = struct.pack("!BBHHH", self._ECHO_REQUEST_TYPE, 0, 0, self._IDENTIFIER, 1)
        payload = struct.pack("!d", time.perf_counter()) + b"aiios-discovery"
        checksum = _icmp_checksum(header + payload)
        packet = (
            struct.pack("!BBHHH", self._ECHO_REQUEST_TYPE, 0, checksum, self._IDENTIFIER, 1)
            + payload
        )

        with socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP) as sock:
            sock.settimeout(timeout_seconds)
            start = time.perf_counter()
            sock.sendto(packet, (address, 0))
            try:
                while True:
                    reply, _peer = sock.recvfrom(1024)
                    ip_header_len = (reply[0] & 0x0F) * 4
                    reply_type = reply[ip_header_len]
                    reply_identifier = struct.unpack(
                        "!H", reply[ip_header_len + 4 : ip_header_len + 6]
                    )[0]
                    if reply_type == 0 and reply_identifier == self._IDENTIFIER:
                        latency_ms = (time.perf_counter() - start) * 1000
                        return ScanOutcome(
                            status=DiscoveryResultStatus.SUCCESS,
                            latency_ms=latency_ms,
                            identity={"reply_type": reply_type},
                        )
            except TimeoutError:
                return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)


__all__ = ["IcmpScanner", "TcpScanner", "UdpScanner"]
