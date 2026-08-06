"""Sanity coverage for `app/api/deps.py`'s dependency factories.

Every route-level HTTP test in this suite exercises most of these
factories already, indirectly, through FastAPI's own dependency
injection. Two kinds of factory never get touched that way, though:

- ``get_db_session``/``get_http_client`` are always overridden by the
  ``app`` fixture (see ``tests/conftest.py``'s own docstring), so their
  *real* bodies never run under any HTTP test.
- ``get_event_publisher``, ``get_api_key_permission_repository``,
  ``get_health_monitor``, ``get_auth_service``, ``get_proxy_service``,
  ``get_statistics_service``, and ``get_report_service`` back routers
  outside this scope (``app/api/proxy.py``, ``app/api/analytics.py``,
  ``app/api/gateway_health.py``), so no test targeting the routers in
  scope here ever calls them.

Per this prompt's own instructions, this file does not re-test what the
HTTP suites already cover -- it only calls each factory directly, with a
minimal stand-in for ``Request`` that exposes the same ``request.app.state
.*`` attributes the real one would, confirming each one builds its
service/repository without error. Every test here is declared ``async``
even where nothing is awaited, purely so the module-level
``pytestmark = pytest.mark.asyncio`` (matching every other file in this
suite) never flags a sync test as misconfigured.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.repositories.apikey import ApiKeyPermissionRepository
from app.services.auth import AuthService
from app.services.health import HealthMonitorService
from app.services.proxy import ProxyService
from app.services.reporting import ReportService, StatisticsService

pytestmark = pytest.mark.asyncio


@dataclass
class _FakeRequest:
    """A stand-in for ``starlette.requests.Request``.

    Every factory in ``deps.py`` that takes a ``request`` parameter only
    ever reads ``request.app.state.*`` -- so a real ASGI scope is
    unnecessary here; wrapping the real, lifespan-started ``app`` fixture
    is enough to exercise each factory's own body for real.
    """

    app: FastAPI


class TestGetDbSession:
    async def test_builds_and_yields_a_real_session(self, app: FastAPI) -> None:
        generator = deps.get_db_session(_FakeRequest(app))  # type: ignore[arg-type]
        session = await generator.__anext__()
        assert isinstance(session, AsyncSession)
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()


class TestGetEventPublisher:
    async def test_returns_the_process_wide_publisher(self, app: FastAPI) -> None:
        publisher = deps.get_event_publisher(_FakeRequest(app))  # type: ignore[arg-type]
        assert callable(publisher)
        assert publisher is app.state.publish_event


class TestGetHttpClient:
    async def test_returns_the_process_wide_client(self, app: FastAPI) -> None:
        found = deps.get_http_client(_FakeRequest(app))  # type: ignore[arg-type]
        assert isinstance(found, httpx.AsyncClient)


class TestGetApiKeyPermissionRepository:
    async def test_builds_a_repository_bound_to_the_session(self, db_session: AsyncSession) -> None:
        repo = deps.get_api_key_permission_repository(db_session)
        assert isinstance(repo, ApiKeyPermissionRepository)


class TestGetHealthMonitor:
    async def test_builds_a_monitor_sharing_process_wide_breakers(
        self, app: FastAPI, db_session: AsyncSession
    ) -> None:
        monitor = deps.get_health_monitor(db_session, _FakeRequest(app))  # type: ignore[arg-type]
        assert isinstance(monitor, HealthMonitorService)


class TestGetAuthService:
    async def test_builds_a_service_with_the_jwt_public_key(
        self, app: FastAPI, db_session: AsyncSession
    ) -> None:
        api_keys = deps.get_api_key_service(db_session)
        auth = deps.get_auth_service(_FakeRequest(app), api_keys)  # type: ignore[arg-type]
        assert isinstance(auth, AuthService)


class TestGetProxyService:
    async def test_builds_a_proxy_service_from_every_collaborator(
        self, app: FastAPI, db_session: AsyncSession
    ) -> None:
        fake_request = _FakeRequest(app)
        http_client = deps.get_http_client(fake_request)  # type: ignore[arg-type]
        routes = deps.get_route_service(db_session)
        services = deps.get_service_registry(db_session)
        rate_limits = deps.get_rate_limit_service(db_session, fake_request)  # type: ignore[arg-type]
        quotas = deps.get_quota_service(db_session)
        health = deps.get_health_monitor(db_session, fake_request)  # type: ignore[arg-type]
        transformations = deps.get_transformation_service(db_session)
        publish_event = deps.get_event_publisher(fake_request)  # type: ignore[arg-type]

        proxy = deps.get_proxy_service(
            db_session,
            http_client,
            routes,
            services,
            rate_limits,
            quotas,
            health,
            transformations,
            publish_event,
            fake_request,  # type: ignore[arg-type]
        )
        assert isinstance(proxy, ProxyService)


class TestGetStatisticsService:
    async def test_builds_a_service_bound_to_the_session(self, db_session: AsyncSession) -> None:
        stats = deps.get_statistics_service(db_session)
        assert isinstance(stats, StatisticsService)


class TestGetReportService:
    async def test_builds_a_service_using_the_configured_max_rows(
        self, app: FastAPI, db_session: AsyncSession
    ) -> None:
        report_service = deps.get_report_service(db_session, _FakeRequest(app))  # type: ignore[arg-type]
        assert isinstance(report_service, ReportService)
        assert report_service._max_rows == app.state.service_settings.max_report_rows


class TestGetAuditService:
    async def test_builds_a_service_with_the_apps_session_factory(
        self, app: FastAPI, db_session: AsyncSession
    ) -> None:
        audit = deps.get_audit_service(_FakeRequest(app), db_session)  # type: ignore[arg-type]
        assert audit._session_factory is app.state.db_session_factory


class TestEveryOtherFactoryBuildsWithoutError:
    """The remaining, already request-scoped factories -- one call each,
    for the same "confirm it builds" sanity this module is for, without
    duplicating the HTTP-level assertions the other test files already
    make about their *behaviour*.
    """

    async def test_service_registry(self, db_session: AsyncSession) -> None:
        assert deps.get_service_registry(db_session) is not None

    async def test_version_service(self, db_session: AsyncSession) -> None:
        assert deps.get_version_service(db_session) is not None

    async def test_route_service(self, db_session: AsyncSession) -> None:
        assert deps.get_route_service(db_session) is not None

    async def test_client_service(self, db_session: AsyncSession) -> None:
        assert deps.get_client_service(db_session) is not None

    async def test_api_key_service(self, db_session: AsyncSession) -> None:
        assert deps.get_api_key_service(db_session) is not None

    async def test_rate_limit_service(self, app: FastAPI, db_session: AsyncSession) -> None:
        assert deps.get_rate_limit_service(db_session, _FakeRequest(app)) is not None  # type: ignore[arg-type]

    async def test_quota_service(self, db_session: AsyncSession) -> None:
        assert deps.get_quota_service(db_session) is not None

    async def test_transformation_service(self, db_session: AsyncSession) -> None:
        assert deps.get_transformation_service(db_session) is not None
