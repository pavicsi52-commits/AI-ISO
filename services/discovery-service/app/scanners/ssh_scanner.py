"""SSH scanner, via ``paramiko``.

Live-verified against a real ``openssh-server`` container spun up for
this package's own test suite (``tests/test_scanner_ssh.py``) -- a
genuine SSH handshake and (when a credential is supplied) a genuine
password authentication attempt, not a banner-only check.
"""

from __future__ import annotations

import asyncio
import io
import socket
import time

import paramiko

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 22


class SshScanner(ProtocolScanner):
    """Connects over SSH, reports the server's version banner, and
    authenticates if a credential is supplied.
    """

    protocol = ProtocolType.SSH

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._connect, address, port or _DEFAULT_PORT, timeout_seconds, credential
        )

    def _connect(
        self, address: str, port: int, timeout_seconds: float, credential: ScanCredential | None
    ) -> ScanOutcome:
        start = time.perf_counter()
        # paramiko.Transport((address, port)) connects internally using the
        # OS's default socket timeout, ignoring *timeout_seconds* entirely --
        # an unreachable host would block for the OS default (tens of
        # seconds) instead of the caller's requested timeout. Connecting the
        # socket ourselves first, with a real timeout, and handing the
        # already-connected socket to Transport (which paramiko documents as
        # a supported constructor argument) fixes both that and the
        # resulting TIMEOUT/UNREACHABLE misclassification as generic FAILURE.
        try:
            sock = socket.create_connection((address, port), timeout=timeout_seconds)
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        transport: paramiko.Transport | None = None
        try:
            transport = paramiko.Transport(sock)
            transport.banner_timeout = timeout_seconds
            transport.start_client(timeout=timeout_seconds)
        except paramiko.SSHException as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        try:
            remote_version = transport.remote_version
            identity: dict[str, object] = {"server_version": remote_version}

            if credential is not None and credential.username:
                try:
                    if credential.private_key:
                        key = self._load_private_key(credential.private_key)
                        transport.auth_publickey(credential.username, key)
                    elif credential.password:
                        transport.auth_password(credential.username, credential.password)
                    identity["authenticated"] = True
                except paramiko.AuthenticationException:
                    latency_ms = (time.perf_counter() - start) * 1000
                    return ScanOutcome(
                        status=DiscoveryResultStatus.AUTH_FAILED,
                        latency_ms=latency_ms,
                        identity=identity,
                    )

            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS, latency_ms=latency_ms, identity=identity
            )
        finally:
            transport.close()

    @staticmethod
    def _load_private_key(pem: str) -> paramiko.PKey:
        return paramiko.RSAKey.from_private_key(io.StringIO(pem))


__all__ = ["SshScanner"]
