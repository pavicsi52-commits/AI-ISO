"""Direct tests for the dependency-injection factory functions in
:mod:`app.api.deps` that no router currently reaches.

``get_db_session`` is overridden by the ``app``/``client`` fixtures in
every other test (so a real request never runs its own body), and
``get_notification_manager``/``get_notification_service`` plus the
category/variable/script/role/collection/review/signature service
factories back capabilities docs/041 scopes to this service's own
domain model without giving any of them a dedicated top-level REST
endpoint of their own (the same "wired but unrouted" shape
``test_schemas_unrouted.py`` documents for their schemas). Each is
still real, request-scoped DI wiring and is exercised directly here
against a real Starlette ``Request`` bound to the fully-lifespanned
``app`` fixture, exactly the object FastAPI would have built for an
actual HTTP call.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api import deps
from app.notifications.playbook_notifications import PlaybookNotificationService
from app.services.category import PlaybookCategoryService
from app.services.collection import PlaybookCollectionService
from app.services.review import PlaybookReviewService
from app.services.role import PlaybookRoleService
from app.services.script import PlaybookScriptService
from app.services.signature import PlaybookSignatureService
from app.services.variable import PlaybookVariableService


def _request_for(app: FastAPI) -> Request:
    return Request(scope={"type": "http", "app": app})


class TestDbSessionAndNotificationWiring:
    async def test_get_db_session_yields_a_working_session(self, app: FastAPI) -> None:
        request = _request_for(app)
        async for session in deps.get_db_session(request):
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1

    def test_get_notification_manager_reads_app_state(self, app: FastAPI) -> None:
        manager = deps.get_notification_manager(_request_for(app))
        assert manager is app.state.notification_manager

    def test_get_notification_service_wraps_manager(self, app: FastAPI) -> None:
        manager = deps.get_notification_manager(_request_for(app))
        service = deps.get_notification_service(manager)
        assert isinstance(service, PlaybookNotificationService)


class TestUnroutedServiceFactories:
    def test_get_category_service(self, db_session: AsyncSession) -> None:
        assert isinstance(deps.get_category_service(db_session), PlaybookCategoryService)

    def test_get_variable_service(self, db_session: AsyncSession) -> None:
        assert isinstance(deps.get_variable_service(db_session), PlaybookVariableService)

    def test_get_script_service(self, db_session: AsyncSession) -> None:
        assert isinstance(deps.get_script_service(db_session), PlaybookScriptService)

    def test_get_role_service(self, db_session: AsyncSession) -> None:
        assert isinstance(deps.get_role_service(db_session), PlaybookRoleService)

    def test_get_collection_service(self, db_session: AsyncSession) -> None:
        assert isinstance(deps.get_collection_service(db_session), PlaybookCollectionService)

    def test_get_review_service(self, db_session: AsyncSession) -> None:
        assert isinstance(deps.get_review_service(db_session), PlaybookReviewService)

    def test_get_signature_service(self, app: FastAPI, db_session: AsyncSession) -> None:
        service = deps.get_signature_service(_request_for(app), db_session)
        assert isinstance(service, PlaybookSignatureService)


__all__: list[str] = []
