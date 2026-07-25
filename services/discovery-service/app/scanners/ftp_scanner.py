"""FTP scanner, via the stdlib ``ftplib``.

Live-verified against a real local ``pyftpdlib`` server
(``tests/test_scanner_ftp.py``) -- a genuine FTP control-channel
handshake and, when a credential is supplied, a genuine ``USER``/
``PASS`` login attempt.
"""

from __future__ import annotations

import asyncio
import ftplib
import time

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 21


class FtpScanner(ProtocolScanner):
    """Connects over FTP and logs in (anonymously, or with a credential)."""

    protocol = ProtocolType.FTP

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
        client = ftplib.FTP()
        try:
            welcome = client.connect(address, port, timeout=timeout_seconds)
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        try:
            username = (credential.username if credential else None) or "anonymous"
            password = (credential.password if credential else None) or "anonymous@"
            try:
                client.login(username, password)
            except ftplib.error_perm:
                latency_ms = (time.perf_counter() - start) * 1000
                return ScanOutcome(
                    status=DiscoveryResultStatus.AUTH_FAILED,
                    latency_ms=latency_ms,
                    identity={"welcome": welcome},
                )

            system = client.sendcmd("SYST")
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"welcome": welcome, "system": system},
            )
        finally:
            try:
                client.quit()
            except OSError:
                client.close()


__all__ = ["FtpScanner"]
