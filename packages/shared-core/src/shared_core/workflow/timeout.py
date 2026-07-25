"""Timeout handling.

Per docs/028_Enterprise_Workflow_SDK.md.txt "TIMEOUTS": Task Timeout,
Workflow Timeout, Connector Timeout, Approval Timeout, AI Timeout,
Queue Timeout. Thin :func:`asyncio.wait_for` wrapper translating a bare
``TimeoutError`` into this SDK's own
:class:`~shared_core.workflow.exceptions.WorkflowTimeoutError`,
matching :mod:`shared_core.connectors.timeout`'s identical pattern.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from shared_core.workflow.exceptions import WorkflowTimeoutError


async def with_timeout[T](awaitable: Awaitable[T], *, timeout_seconds: float, operation: str) -> T:
    """Await *awaitable*, raising :class:`WorkflowTimeoutError` past *timeout_seconds*.

    Raises:
        WorkflowTimeoutError: If the timeout elapses first.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as exc:
        raise WorkflowTimeoutError(f"{operation} exceeded its {timeout_seconds}s timeout.") from exc


__all__ = ["with_timeout"]
