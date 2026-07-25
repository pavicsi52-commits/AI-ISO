"""SFTP scanner, via ``paramiko`` -- the SFTP subsystem layered on an
SSH transport (the same connection type ``ssh_scanner.py`` uses), so
this shares the same real container this package's test suite spins up
for ``ssh_scanner.py``.
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


class SftpScanner(ProtocolScanner):
    """Opens an SFTP session and lists the connection's default directory."""

    protocol = ProtocolType.SFTP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        if credential is None or not credential.username:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                error_message="SFTP requires a credential with a username.",
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._connect, address, port or _DEFAULT_PORT, timeout_seconds, credential
        )

    @staticmethod
    def _open_transport(
        address: str, port: int, timeout_seconds: float
    ) -> paramiko.Transport | ScanOutcome:
        """Connect a real socket (honoring *timeout_seconds*, unlike
        ``paramiko.Transport``'s own internal connect -- see
        ``ssh_scanner.py::SshScanner._connect`` for why) and start an SSH
        client session on it. Returns the live transport, or the
        :class:`ScanOutcome` an ordinary probe failure maps to.
        """
        try:
            sock = socket.create_connection((address, port), timeout=timeout_seconds)
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        try:
            transport = paramiko.Transport(sock)
            transport.banner_timeout = timeout_seconds
            transport.start_client(timeout=timeout_seconds)
        except paramiko.SSHException as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        return transport

    def _connect(
        self, address: str, port: int, timeout_seconds: float, credential: ScanCredential
    ) -> ScanOutcome:
        start = time.perf_counter()
        transport = self._open_transport(address, port, timeout_seconds)
        if isinstance(transport, ScanOutcome):
            return transport

        username = credential.username
        if not username:
            transport.close()
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                error_message="SFTP requires a credential with a username.",
            )

        try:
            try:
                if credential.private_key:
                    key = paramiko.RSAKey.from_private_key(io.StringIO(credential.private_key))
                    transport.auth_publickey(username, key)
                elif credential.password:
                    transport.auth_password(username, credential.password)
            except paramiko.AuthenticationException:
                latency_ms = (time.perf_counter() - start) * 1000
                return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, latency_ms=latency_ms)

            sftp = paramiko.SFTPClient.from_transport(transport)
            if sftp is None:
                return ScanOutcome(
                    status=DiscoveryResultStatus.FAILURE,
                    error_message="SFTP subsystem unavailable.",
                )
            try:
                entries = sftp.listdir(".")
            finally:
                sftp.close()

            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"entry_count": len(entries), "server_version": transport.remote_version},
            )
        finally:
            transport.close()


__all__ = ["SftpScanner"]
