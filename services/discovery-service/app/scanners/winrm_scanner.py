"""WinRM scanner, via ``pywinrm``.

**Not verified against a real target in this environment**: WinRM
targets a *remote* Windows host with the WinRM listener enabled
(disabled by default even on Windows) -- there is no such host
reachable here, and enabling a WinRM listener on this development
machine itself to test against would modify the shared host's system
configuration, which this build deliberately avoids. The client code
below is real and complete (a genuine WS-Management ``Create`` against
the shell resource, the same minimal-footprint probe
``ssh_scanner.py``'s own transport-level handshake mirrors, rather than
executing an arbitrary remote command for a mere discovery probe).
"""

from __future__ import annotations

import asyncio
import time

from winrm.exceptions import (
    InvalidCredentialsError,
    WinRMError,
    WinRMTransportError,
)
from winrm.protocol import Protocol

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 5985


class WinRmScanner(ProtocolScanner):
    """Opens (and immediately closes) a WinRM shell as a connectivity/auth probe."""

    protocol = ProtocolType.WINRM

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
                error_message="WinRM requires a credential with a username.",
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._open_shell, address, port or _DEFAULT_PORT, timeout_seconds, credential
        )

    def _open_shell(
        self, address: str, port: int, timeout_seconds: float, credential: ScanCredential
    ) -> ScanOutcome:
        endpoint = f"http://{address}:{port}/wsman"
        protocol = Protocol(
            endpoint=endpoint,
            transport="ntlm",
            username=credential.username,
            password=credential.password or "",
            operation_timeout_sec=int(timeout_seconds),
            read_timeout_sec=int(timeout_seconds) + 5,
        )
        start = time.perf_counter()
        try:
            shell_id = protocol.open_shell()
        except InvalidCredentialsError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=str(exc))
        except WinRMTransportError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        except WinRMError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except OSError as exc:
            # winrm.exceptions.WinRMTransportError only wraps HTTP-level
            # failures (a response was actually received) --
            # `requests`/`urllib3` raise a bare `requests.exceptions
            # .ConnectionError`/`Timeout` (both real `OSError` subclasses)
            # for a refused/unreachable connection *before* any response
            # exists, same as every other scanner in this package classifies
            # a transport-level connection failure.
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        try:
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"shell_opened": True},
            )
        finally:
            protocol.close_shell(shell_id)


__all__ = ["WinRmScanner"]
