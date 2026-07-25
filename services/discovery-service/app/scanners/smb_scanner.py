"""SMB scanner, via ``smbprotocol``.

**Not verified against a real SMB server in this environment**: no
Samba/Windows file-sharing server is part of this repository's
docker-compose stack, and standing one up brings in a heavier test
dependency (a full Samba container plus user provisioning) than the
scanner itself justifies for one protocol among many in this package.
The client code below is real and complete -- a genuine SMB2 session
negotiation and tree connect against the administrative ``IPC$``
share, the same minimal-footprint "prove the protocol and the
credential both work" probe every other scanner in this package uses
-- but, unlike most of this package's scanners, was not exercised
against a live server here.
"""

from __future__ import annotations

import asyncio
import time

import smbclient
from smbprotocol.exceptions import LogonFailure, SMBException

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 445


class SmbScanner(ProtocolScanner):
    """Negotiates an SMB2 session and lists the administrative ``IPC$`` share."""

    protocol = ProtocolType.SMB

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
        connection_cache: dict[str, object] = {}
        start = time.perf_counter()
        try:
            smbclient.register_session(
                address,
                username=credential.username if credential else None,
                password=credential.password if credential else None,
                port=port,
                connection_timeout=timeout_seconds,
                connection_cache=connection_cache,
            )
            entries = list(
                smbclient.listdir(rf"\\{address}\IPC$", connection_cache=connection_cache)
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={"ipc_entry_count": len(entries)},
            )
        except LogonFailure as exc:
            return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=str(exc))
        except SMBException as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        except ValueError as exc:
            # smbprotocol.transport.Tcp.connect() deliberately wraps the
            # real socket-level OSError/socket.gaierror (refused
            # connection, unreachable host, DNS failure) in a bare
            # ValueError rather than letting it propagate or raising an
            # SMBException -- so it must be classified here too, the same
            # connection failure the `except OSError` clause above handles.
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        finally:
            smbclient.reset_connection_cache(connection_cache=connection_cache)


__all__ = ["SmbScanner"]
