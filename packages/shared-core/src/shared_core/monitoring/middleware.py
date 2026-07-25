"""Application monitoring middleware.

ASGI middleware feeding
:class:`shared_core.monitoring.application.ApplicationStatistics` from
real request traffic -- "Request Count", "Response Time", "Error Count"
per docs/023_Enterprise_Monitoring_Framework.md.txt "APPLICATION
MONITORING". Same raw-ASGI shape as
:class:`shared_core.middleware.timing.TimingMiddleware` (Prompt 012).
"""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared_core.monitoring.application import ApplicationStatistics

_HTTP_SERVER_ERROR_STATUS: int = 500


class ApplicationMonitoringMiddleware:
    """ASGI middleware recording every request into an :class:`ApplicationStatistics` tracker."""

    def __init__(self, app: ASGIApp, *, statistics: ApplicationStatistics) -> None:
        self._app = app
        self._statistics = statistics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, capture_status)
        except Exception:
            self._statistics.record_exception()
            raise
        finally:
            response_time_ms = (time.perf_counter() - start) * 1000
            self._statistics.record_request(response_time_ms)
            if status_code >= _HTTP_SERVER_ERROR_STATUS:
                self._statistics.record_error()


__all__ = ["ApplicationMonitoringMiddleware"]
