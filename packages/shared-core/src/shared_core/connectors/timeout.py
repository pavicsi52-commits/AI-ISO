"""Timeout handling.

Per docs/027_Enterprise_Connector_SDK.md.txt "CONNECTION MANAGEMENT"/
"COMMAND EXECUTION": Timeouts. Thin :func:`asyncio.wait_for` wrapper
translating a bare ``TimeoutError`` into this SDK's own
:class:`~shared_core.connectors.exceptions.ConnectorTimeoutError`, so
callers catching this SDK's exception hierarchy don't need to know
timeouts happen to be implemented via :func:`asyncio.wait_for`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from shared_core.connectors.exceptions import ConnectorTimeoutError


async def with_timeout[T](awaitable: Awaitable[T], *, timeout_seconds: float, operation: str) -> T:
    """Await *awaitable*, raising :class:`ConnectorTimeoutError` past *timeout_seconds*.

    Raises:
        ConnectorTimeoutError: If the timeout elapses first.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as exc:
        raise ConnectorTimeoutError(
            f"{operation} exceeded its {timeout_seconds}s timeout."
        ) from exc


__all__ = ["with_timeout"]
