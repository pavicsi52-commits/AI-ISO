"""Tests for cross-cutting decorators."""

from __future__ import annotations

import uuid

import pytest
from shared_core.database import Base, create_session_factory, create_test_engine
from shared_core.decorators import (
    audit,
    rate_limited,
    requires_organization,
    requires_permission,
    requires_project,
    requires_role,
    transactional,
    validates,
)
from shared_core.enums import AuditAction, Permission, Role
from shared_core.exceptions import AuthorizationError, RateLimitError, ValidationError
from shared_core.security.context import bind_security_context, reset_security_context
from shared_core.validators import validate_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


@pytest.fixture(autouse=True)
def _reset_security() -> None:
    reset_security_context()
    yield
    reset_security_context()


# --- requires_permission / requires_role ---


async def test_requires_permission_allows_when_role_grants_it() -> None:
    bind_security_context(role=Role.OPERATOR)

    @requires_permission(Permission.CREATE)
    async def create_thing() -> str:
        return "created"

    assert await create_thing() == "created"


async def test_requires_permission_denies_when_role_lacks_it() -> None:
    bind_security_context(role=Role.VIEWER)

    @requires_permission(Permission.DELETE)
    async def delete_thing() -> str:
        return "deleted"

    with pytest.raises(AuthorizationError):
        await delete_thing()


async def test_requires_permission_denies_when_unauthenticated() -> None:
    @requires_permission(Permission.READ)
    async def read_thing() -> str:
        return "read"

    with pytest.raises(AuthorizationError):
        await read_thing()


async def test_requires_role_allows_matching_role() -> None:
    bind_security_context(role=Role.PROJECT_ADMIN)

    @requires_role(Role.PROJECT_ADMIN)
    async def admin_action() -> str:
        return "done"

    assert await admin_action() == "done"


async def test_requires_role_allows_super_admin_override() -> None:
    bind_security_context(role=Role.SUPER_ADMIN)

    @requires_role(Role.PROJECT_ADMIN)
    async def admin_action() -> str:
        return "done"

    assert await admin_action() == "done"


async def test_requires_role_denies_mismatched_role() -> None:
    bind_security_context(role=Role.VIEWER)

    @requires_role(Role.PROJECT_ADMIN)
    async def admin_action() -> str:
        return "done"

    with pytest.raises(AuthorizationError):
        await admin_action()


async def test_requires_organization_allows_when_scoped() -> None:
    bind_security_context(organization_id=uuid.uuid4())

    @requires_organization()
    async def scoped_action() -> str:
        return "done"

    assert await scoped_action() == "done"


async def test_requires_organization_denies_when_unscoped() -> None:
    @requires_organization()
    async def scoped_action() -> str:
        return "done"

    with pytest.raises(AuthorizationError):
        await scoped_action()


async def test_requires_project_allows_when_scoped() -> None:
    bind_security_context(project_id=uuid.uuid4())

    @requires_project()
    async def scoped_action() -> str:
        return "done"

    assert await scoped_action() == "done"


async def test_requires_project_denies_when_unscoped() -> None:
    @requires_project()
    async def scoped_action() -> str:
        return "done"

    with pytest.raises(AuthorizationError):
        await scoped_action()


# --- audit ---


async def test_audit_logs_and_returns_result_on_success() -> None:
    @audit(AuditAction.CREATE)
    async def create_thing() -> str:
        return "created"

    assert await create_thing() == "created"


async def test_audit_logs_and_reraises_on_failure() -> None:
    @audit(AuditAction.DELETE)
    async def delete_thing() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await delete_thing()


# --- transactional ---


class _Widget(Base):
    __tablename__ = "decorator_test_widgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column()


@pytest.fixture
async def engine():  # type: ignore[no-untyped-def]
    engine = create_test_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


async def test_transactional_commits_on_success(session: AsyncSession) -> None:
    widget_id = uuid.uuid4()

    @transactional
    async def create_widget(session: AsyncSession) -> None:
        session.add(_Widget(id=widget_id, name="thing"))

    await create_widget(session)

    result = await session.execute(select(_Widget).where(_Widget.id == widget_id))
    assert result.scalar_one_or_none() is not None


async def test_transactional_rolls_back_on_error(session: AsyncSession) -> None:
    @transactional
    async def create_widget(session: AsyncSession) -> None:
        session.add(_Widget(id=uuid.uuid4(), name="thing"))
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await create_widget(session)

    result = await session.execute(select(_Widget))
    assert result.first() is None


async def test_transactional_requires_a_session_argument() -> None:
    @transactional
    async def no_session_here() -> None:
        return None

    with pytest.raises(TypeError, match="AsyncSession"):
        await no_session_here()


# --- validates ---


async def test_validates_allows_valid_input() -> None:
    @validates("email", validate_email)
    async def register(*, email: str) -> str:
        return email

    assert await register(email="user@example.com") == "user@example.com"


async def test_validates_rejects_invalid_input() -> None:
    @validates("email", validate_email)
    async def register(*, email: str) -> str:
        return email

    with pytest.raises(ValidationError):
        await register(email="not-an-email")


async def test_validates_skips_check_when_argument_absent() -> None:
    @validates("email", validate_email)
    async def register(**kwargs: str) -> str:
        return "ok"

    assert await register() == "ok"


# --- rate_limited ---


async def test_rate_limited_allows_up_to_the_limit() -> None:
    @rate_limited(key="test-op", max_requests=2, window_seconds=60)
    async def call_external_api() -> str:
        return "ok"

    assert await call_external_api() == "ok"
    assert await call_external_api() == "ok"

    with pytest.raises(RateLimitError):
        await call_external_api()
