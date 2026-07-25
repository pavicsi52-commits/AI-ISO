"""MQTT scanner, via ``aiomqtt``.

Live-verified against a real Eclipse Mosquitto broker container
(``tests/test_scanner_mqtt.py``) -- a genuine MQTT CONNECT/CONNACK
handshake.
"""

from __future__ import annotations

import time
import uuid

import aiomqtt

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 1883


class MqttScanner(ProtocolScanner):
    """Connects to an MQTT broker and reports the CONNACK outcome."""

    protocol = ProtocolType.MQTT

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        start = time.perf_counter()
        client_id = f"aiios-discovery-{uuid.uuid4().hex[:12]}"
        try:
            async with aiomqtt.Client(
                hostname=address,
                port=port or _DEFAULT_PORT,
                identifier=client_id,
                username=credential.username if credential else None,
                password=credential.password if credential else None,
                timeout=timeout_seconds,
            ):
                latency_ms = (time.perf_counter() - start) * 1000
                return ScanOutcome(
                    status=DiscoveryResultStatus.SUCCESS,
                    latency_ms=latency_ms,
                    identity={"client_id": client_id},
                )
        except aiomqtt.MqttCodeError as exc:
            if exc.rc in (4, 5):  # bad username/password, not authorized
                return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=str(exc))
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))
        except TimeoutError:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except aiomqtt.MqttError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))


__all__ = ["MqttScanner"]
