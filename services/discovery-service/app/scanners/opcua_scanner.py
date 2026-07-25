"""OPC UA scanner, via ``asyncua``.

Live-verified against a real in-process ``asyncua.Server``
(``tests/test_scanner_opcua.py``) -- a genuine OPC UA
``GetEndpoints``/session handshake, reading the server's real
``ServerStatus`` node.
"""

from __future__ import annotations

import time

from asyncua.client.client import Client
from asyncua.ua.uaerrors import UaError

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 4840


class OpcUaScanner(ProtocolScanner):
    """Connects to an OPC UA endpoint and reads its server state."""

    protocol = ProtocolType.OPC_UA

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        url = f"opc.tcp://{address}:{port or _DEFAULT_PORT}"
        client = Client(url=url, timeout=timeout_seconds)
        if credential is not None and credential.username:
            client.set_user(credential.username)
            if credential.password:
                client.set_password(credential.password)

        start = time.perf_counter()
        try:
            async with client:
                state = await client.get_node("ns=0;i=2259").read_value()  # ServerStatus.State
                latency_ms = (time.perf_counter() - start) * 1000
                return ScanOutcome(
                    status=DiscoveryResultStatus.SUCCESS,
                    latency_ms=latency_ms,
                    identity={
                        "server_state": str(state),
                        "endpoint": client.server_url.geturl(),
                    },
                )
        except UaError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))


__all__ = ["OpcUaScanner"]
