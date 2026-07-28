"""Dispatches a
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`'s
own ``check_type`` onto the collector logic that actually performs it
("SYNTHETIC MONITORING" "Support"). ``target`` is optional -- a
synthetic test may probe a bare external endpoint with no registered
:class:`~app.models.monitoring_target.MonitoringTarget` of its own (see
that model's own docstring), in which case ``host``/``url``/
``target_external_id`` must be supplied directly in the test's own
``parameters``.

Reuses :mod:`app.collectors.network`'s low-level, model-agnostic
``_tcp_connect``/``_resolve_dns``/``_http_request`` helpers for
``TCP``/``DNS``/``HTTP``/``API`` checks, and
:func:`app.collectors.remote.run_automation_job` for ``SSH``/
``DATABASE``/``CUSTOM_SCRIPT`` checks that genuinely require remote
code execution -- no probing logic is duplicated here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.collectors.network import (
    DEFAULT_TIMEOUT_SECONDS,
    _http_request,
    _resolve_dns,
    _tcp_connect,
)
from app.collectors.remote import run_automation_job
from app.models.enums import SyntheticCheckType
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.models.monitoring_target import MonitoringTarget


def _resolve_host(test: MonitoringSyntheticTest, target: MonitoringTarget | None) -> str:
    host = test.parameters.get("host")
    if host:
        return str(host)
    if target is not None:
        target_host = target.target_metadata.get("host")
        if target_host:
            return str(target_host)
    raise ValidationError(
        f"Synthetic test {test.id!r} has no 'host' in its own parameters and its target "
        "(if any) has no 'host' in its own target_metadata."
    )


async def _run_tcp(
    test: MonitoringSyntheticTest, target: MonitoringTarget | None, _context: CollectorContext
) -> dict[str, Any]:
    host = _resolve_host(test, target)
    port = int(test.parameters.get("port", 443))
    timeout_seconds = float(test.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    return await _tcp_connect(host, port, timeout_seconds=timeout_seconds)


async def _run_dns(
    test: MonitoringSyntheticTest, target: MonitoringTarget | None, _context: CollectorContext
) -> dict[str, Any]:
    host = _resolve_host(test, target)
    timeout_seconds = float(test.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    return await _resolve_dns(host, timeout_seconds=timeout_seconds)


async def _run_http(
    test: MonitoringSyntheticTest, _target: MonitoringTarget | None, _context: CollectorContext
) -> dict[str, Any]:
    url = test.parameters.get("url")
    if not url:
        raise ValidationError(
            f"Synthetic test {test.id!r} (check_type {test.check_type!r}) has no 'url' in its "
            "own parameters."
        )
    return await _http_request(
        str(url),
        method=str(test.parameters.get("method", "GET")).upper(),
        timeout_seconds=float(test.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        expected_status=int(test.parameters.get("expected_status", 200)),
        body_contains=test.parameters.get("body_contains"),
    )


async def _run_automation(
    test: MonitoringSyntheticTest, target: MonitoringTarget | None, context: CollectorContext
) -> dict[str, Any]:
    job_id_raw = test.parameters.get("job_id")
    if job_id_raw is None:
        raise ValidationError(
            f"Synthetic test {test.id!r} (check_type {test.check_type!r}) has no 'job_id' in "
            "its own parameters."
        )
    target_external_id = test.parameters.get("target_external_id")
    if not target_external_id and target is not None:
        target_external_id = target.external_id
    if not target_external_id:
        raise ValidationError(
            f"Synthetic test {test.id!r} has no 'target_external_id' in its own parameters and "
            "no registered target to derive one from."
        )
    return await run_automation_job(context, UUID(str(job_id_raw)), str(target_external_id))


_DISPATCH: dict[
    SyntheticCheckType,
    Callable[
        [MonitoringSyntheticTest, MonitoringTarget | None, CollectorContext],
        Awaitable[dict[str, Any]],
    ],
] = {
    SyntheticCheckType.HTTP: _run_http,
    SyntheticCheckType.API: _run_http,
    SyntheticCheckType.TCP: _run_tcp,
    SyntheticCheckType.DNS: _run_dns,
    SyntheticCheckType.SSH: _run_automation,
    SyntheticCheckType.DATABASE: _run_automation,
    SyntheticCheckType.CUSTOM_SCRIPT: _run_automation,
}


async def run_synthetic_test(
    test: MonitoringSyntheticTest, target: MonitoringTarget | None, context: CollectorContext
) -> dict[str, Any]:
    """Run *test* and return its own collected result.

    Raises:
        ValidationError: If *test*'s own ``check_type`` has no registered handler.
    """
    handler = _DISPATCH.get(test.check_type)
    if handler is None:
        raise ValidationError(
            f"Synthetic test {test.id!r} has unsupported check_type " f"{test.check_type!r}."
        )
    return await handler(test, target, context)


__all__ = ["run_synthetic_test"]
