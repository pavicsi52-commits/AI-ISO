"""Tests for :class:`app.scanners.mqtt_scanner.MqttScanner`.

The CONNECT/CONNACK success path is verified against the real Eclipse
Mosquitto broker container this package's own test suite starts (see
``tests/conftest.py``'s own module docstring). The broker allows
anonymous access, so the auth-failure/timeout branches (which a
"anonymous access enabled" broker can never actually produce) are
exercised by monkeypatching ``aiomqtt.Client`` to raise the exact
exception types ``aiomqtt`` itself raises for those cases -- the real
request-building/response-classification logic still runs, only the
network round trip is stubbed.

``aiomqtt``'s underlying ``paho-mqtt`` transport calls
``loop.add_reader()``/``add_writer()``, which Windows' default
``ProactorEventLoop`` doesn't implement (``NotImplementedError`` at
socket-registration time, not an application bug). Rather than
overriding pytest-asyncio's own ``event_loop_policy`` fixture (its
1.4.0 internals assert on loop-scope/runner-fixture matching in a way
that a module-scoped override trips) or the equally version-sensitive
``asyncio.get/set_event_loop_policy`` functions (deprecated for
removal in Python 3.16), the two tests that need a real MQTT round
trip construct and run a plain :class:`asyncio.SelectorEventLoop`
directly, bypassing both pytest-asyncio's loop and any process-wide
policy just for those two, synchronous-looking test functions.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiomqtt
import pytest

from app.models.enums import DiscoveryResultStatus
from app.scanners.mqtt_scanner import MqttScanner
from tests.conftest import MQTT_TEST_HOST, MQTT_TEST_PORT


def _run_on_selector_loop(coro: Any) -> Any:
    loop = asyncio.SelectorEventLoop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_probe_succeeds_against_real_broker() -> None:
    async def _run() -> None:
        scanner = MqttScanner()
        outcome = await scanner.probe(
            MQTT_TEST_HOST, port=MQTT_TEST_PORT, timeout_seconds=5, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert outcome.latency_ms is not None
        assert outcome.identity["client_id"]

    _run_on_selector_loop(_run())


def test_probe_unreachable_host() -> None:
    async def _run() -> None:
        scanner = MqttScanner()
        outcome = await scanner.probe(MQTT_TEST_HOST, port=1, timeout_seconds=1, credential=None)
        assert outcome.status in (
            DiscoveryResultStatus.UNREACHABLE,
            DiscoveryResultStatus.TIMEOUT,
        )

    _run_on_selector_loop(_run())


def _raising_client(exc: Exception) -> type:
    class _FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Any:
            raise exc

        async def __aexit__(self, *_args: object) -> None:  # pragma: no cover
            return None

    return _FakeClient


@pytest.mark.parametrize("code", [4, 5])
async def test_probe_bad_credentials_maps_to_auth_failed(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    monkeypatch.setattr(aiomqtt, "Client", _raising_client(aiomqtt.MqttCodeError(code, "denied")))
    scanner = MqttScanner()
    outcome = await scanner.probe(
        MQTT_TEST_HOST, port=MQTT_TEST_PORT, timeout_seconds=5, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.AUTH_FAILED


async def test_probe_other_mqtt_code_error_maps_to_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        aiomqtt, "Client", _raising_client(aiomqtt.MqttCodeError(1, "protocol error"))
    )
    scanner = MqttScanner()
    outcome = await scanner.probe(
        MQTT_TEST_HOST, port=MQTT_TEST_PORT, timeout_seconds=5, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.FAILURE


async def test_probe_timeout_error_maps_to_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aiomqtt, "Client", _raising_client(TimeoutError()))
    scanner = MqttScanner()
    outcome = await scanner.probe(
        MQTT_TEST_HOST, port=MQTT_TEST_PORT, timeout_seconds=5, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.TIMEOUT
