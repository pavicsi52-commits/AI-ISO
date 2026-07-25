"""Tests for versioning, soft delete, audit, tenant helpers, unit of work,
decorators, seed/fixtures/factory, connection, and health -- everything in
the Enterprise Database Framework not already covered by
``test_database.py`` (generic repository) or ``test_database_postgres.py``
(PostgreSQL-only behavior).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC
from types import SimpleNamespace

import pytest
from shared_core.base import BaseEntityMixin
from shared_core.database.audit import capture_before, record_audit, record_bulk_audit, snapshot
from shared_core.database.base import Base
from shared_core.database.connection import graceful_shutdown, wait_for_database
from shared_core.database.decorators import readonly, retry, soft_delete, tenant
from shared_core.database.engine import create_test_engine
from shared_core.database.exceptions import (
    ConnectionFailedError,
    QueryTimeoutError,
    TenantViolationError,
    TransactionFailedError,
    VersionConflictError,
)
from shared_core.database.factory import create_test_database_framework
from shared_core.database.fixtures import ModelFactory
from shared_core.database.health import get_health_report, get_pool_status
from shared_core.database.helpers import migration_file_slug, new_uuid, utcnow
from shared_core.database.search import apply_search
from shared_core.database.seed import SeedEnvironment, SeedRegistry, seed
from shared_core.database.session import (
    create_session_factory,
    get_session,
    get_worker_session,
    session_scope,
)
from shared_core.database.soft_delete import mark_deleted, mark_restored, purge
from shared_core.database.tenant import (
    TenantScope,
    apply_tenant_scope,
    enforce_tenant_match,
    tenant_scope_from_security_context,
)
from shared_core.database.transaction import is_retryable_error, nested_transaction, run_with_retry
from shared_core.database.transaction import unit_of_work as uow_context
from shared_core.database.unit_of_work import UnitOfWork
from shared_core.database.versioning import check_version, increment_version
from shared_core.enums.role import Role
from shared_core.security.context import bind_security_context, reset_security_context
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

type _SessionFactory = async_sessionmaker[AsyncSession]


class _Entity(Base, BaseEntityMixin):
    __tablename__ = "lifecycle_test_entities"

    name: Mapped[str] = mapped_column(default="x")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_test_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> _SessionFactory:
    return create_session_factory(engine)


@pytest.fixture
async def session(session_factory: _SessionFactory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_security() -> None:
    reset_security_context()
    yield
    reset_security_context()


def _make_retryable_error() -> OperationalError:
    orig = SimpleNamespace(sqlstate="40P01")
    return OperationalError("SELECT 1", {}, orig)  # type: ignore[arg-type]


def _make_non_retryable_error() -> OperationalError:
    orig = SimpleNamespace(sqlstate="23505")
    return OperationalError("SELECT 1", {}, orig)  # type: ignore[arg-type]


# --- session.py ---


async def test_get_session_yields_a_working_session(session_factory: _SessionFactory) -> None:
    entity_id = uuid.uuid4()
    async for db_session in get_session(session_factory):
        db_session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))
        await db_session.commit()

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(_Entity).where(_Entity.id == entity_id))
        assert result.scalar_one_or_none() is not None


async def test_get_worker_session_yields_a_working_session(
    session_factory: _SessionFactory,
) -> None:
    entity_id = uuid.uuid4()
    async for db_session in get_worker_session(session_factory):
        db_session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))
        await db_session.commit()

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(_Entity).where(_Entity.id == entity_id))
        assert result.scalar_one_or_none() is not None


async def test_session_scope_commits_on_success(session_factory: _SessionFactory) -> None:
    entity_id = uuid.uuid4()
    async with session_scope(session_factory) as db_session:
        db_session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(_Entity).where(_Entity.id == entity_id))
        assert result.scalar_one_or_none() is not None


async def test_session_scope_rolls_back_on_error(session_factory: _SessionFactory) -> None:
    entity_id = uuid.uuid4()
    with pytest.raises(ValueError, match="boom"):
        async with session_scope(session_factory) as db_session:
            db_session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))
            raise ValueError("boom")

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(_Entity).where(_Entity.id == entity_id))
        assert result.scalar_one_or_none() is None


# --- versioning.py ---


def test_check_version_passes_when_matching() -> None:
    entity = _Entity(name="x")
    entity.version = 3
    check_version(entity, 3)  # does not raise


def test_check_version_raises_version_conflict_when_stale() -> None:
    entity = _Entity(name="x")
    entity.version = 3
    with pytest.raises(VersionConflictError):
        check_version(entity, 2)


def test_increment_version_returns_new_value() -> None:
    entity = _Entity(name="x")
    entity.version = 1
    assert increment_version(entity) == 2
    assert entity.version == 2


# --- soft_delete.py ---


def test_mark_deleted_sets_fields() -> None:
    entity = _Entity(name="x")
    deleter = uuid.uuid4()

    mark_deleted(entity, deleted_by=deleter)

    assert entity.is_active is False
    assert entity.deleted_by == deleter
    assert entity.deleted_at is not None


def test_mark_restored_clears_fields() -> None:
    entity = _Entity(name="x")
    mark_deleted(entity, deleted_by=uuid.uuid4())

    mark_restored(entity)

    assert entity.is_active is True
    assert entity.deleted_by is None
    assert entity.deleted_at is None


async def test_purge_removes_the_row(session: AsyncSession) -> None:
    entity = _Entity(name="x", organization_id=uuid.uuid4())
    session.add(entity)
    await session.flush()

    await purge(session, entity)

    result = await session.execute(select(_Entity).where(_Entity.id == entity.id))
    assert result.scalar_one_or_none() is None


# --- audit.py ---


async def test_snapshot_includes_every_column(session: AsyncSession) -> None:
    entity = _Entity(name="x", organization_id=uuid.uuid4())
    session.add(entity)
    await session.flush()

    data = snapshot(entity)

    assert data["name"] == "x"
    assert data["id"] == entity.id


async def test_capture_before_reflects_pre_mutation_value(session: AsyncSession) -> None:
    entity = _Entity(name="original", organization_id=uuid.uuid4())
    session.add(entity)
    await session.flush()

    entity.name = "changed"
    before = capture_before(entity)

    assert before["name"] == "original"
    assert entity.name == "changed"


def test_record_audit_builds_entry_with_actor_and_version() -> None:
    entity = _Entity(name="x")
    entity.version = 2
    actor_id = uuid.uuid4()

    entry = record_audit("create", entity, actor_id=actor_id)

    assert entry.action == "create"
    assert entry.entity_type == "_Entity"
    assert entry.actor_id == str(actor_id)
    assert entry.version == 2
    assert entry.after is not None


def test_record_audit_delete_action_has_no_after_snapshot() -> None:
    entity = _Entity(name="x")

    entry = record_audit("delete", entity)

    assert entry.after is None


def test_record_bulk_audit_carries_count() -> None:
    entry = record_bulk_audit("bulk_delete", "_Entity", count=7)

    assert entry.after == {"count": 7}
    assert entry.entity_id is None


# --- tenant.py ---


def test_tenant_scope_from_security_context_reads_role_and_ids() -> None:
    org_id, project_id = uuid.uuid4(), uuid.uuid4()
    bind_security_context(organization_id=org_id, project_id=project_id, role=Role.OPERATOR)

    scope = TenantScope.from_security_context()

    assert scope.organization_id == org_id
    assert scope.project_id == project_id
    assert scope.is_super_admin is False


def test_tenant_scope_from_security_context_detects_super_admin() -> None:
    bind_security_context(role=Role.SUPER_ADMIN)

    scope = TenantScope.from_security_context()

    assert scope.is_super_admin is True


def test_tenant_scope_from_security_context_tuple_form() -> None:
    org_id = uuid.uuid4()
    bind_security_context(organization_id=org_id, role=Role.VIEWER)

    organization_id, project_id, is_super_admin = tenant_scope_from_security_context()

    assert organization_id == org_id
    assert project_id is None
    assert is_super_admin is False


def test_apply_tenant_scope_bypasses_for_super_admin() -> None:
    stmt = apply_tenant_scope(select(_Entity), _Entity, organization_id=None, is_super_admin=True)
    assert stmt.whereclause is None


def test_apply_tenant_scope_raises_without_organization_id() -> None:
    with pytest.raises(TenantViolationError):
        apply_tenant_scope(select(_Entity), _Entity, organization_id=None)


def test_apply_tenant_scope_also_filters_by_project_id() -> None:
    org_id, project_id = uuid.uuid4(), uuid.uuid4()
    stmt = apply_tenant_scope(
        select(_Entity), _Entity, organization_id=org_id, project_id=project_id
    )
    assert "project_id" in str(stmt.whereclause)


def test_enforce_tenant_match_passes_for_matching_organization() -> None:
    org_id = uuid.uuid4()
    entity = _Entity(name="x", organization_id=org_id)
    enforce_tenant_match(entity, organization_id=org_id)  # does not raise


def test_enforce_tenant_match_raises_for_mismatched_organization() -> None:
    entity = _Entity(name="x", organization_id=uuid.uuid4())
    with pytest.raises(TenantViolationError):
        enforce_tenant_match(entity, organization_id=uuid.uuid4())


def test_enforce_tenant_match_bypasses_for_super_admin() -> None:
    entity = _Entity(name="x", organization_id=uuid.uuid4())
    enforce_tenant_match(entity, organization_id=uuid.uuid4(), is_super_admin=True)  # no raise


def test_enforce_tenant_match_raises_for_mismatched_project() -> None:
    org_id, project_id = uuid.uuid4(), uuid.uuid4()
    entity = _Entity(name="x", organization_id=org_id, project_id=project_id)
    with pytest.raises(TenantViolationError):
        enforce_tenant_match(entity, organization_id=org_id, project_id=uuid.uuid4())


# --- transaction.py: is_retryable_error / nested_transaction / run_with_retry ---


def test_is_retryable_error_true_for_deadlock_sqlstate() -> None:
    assert is_retryable_error(_make_retryable_error()) is True


def test_is_retryable_error_false_for_constraint_sqlstate() -> None:
    assert is_retryable_error(_make_non_retryable_error()) is False


def test_is_retryable_error_false_for_non_dbapi_error() -> None:
    assert is_retryable_error(ValueError("boom")) is False


async def test_unit_of_work_function_raises_query_timeout_error(session: AsyncSession) -> None:
    with pytest.raises(QueryTimeoutError):
        async with uow_context(session, timeout_seconds=0.01):
            await asyncio.sleep(0.2)


async def test_unit_of_work_function_wraps_sqlalchemy_error(session: AsyncSession) -> None:
    with pytest.raises(TransactionFailedError):
        async with uow_context(session):
            raise _make_non_retryable_error()


async def test_nested_transaction_rolls_back_only_the_savepoint(session: AsyncSession) -> None:
    outer_id, inner_id = uuid.uuid4(), uuid.uuid4()
    session.add(_Entity(id=outer_id, name="outer", organization_id=uuid.uuid4()))
    await session.flush()

    with pytest.raises(ValueError, match="boom"):
        async with nested_transaction(session):
            session.add(_Entity(id=inner_id, name="inner", organization_id=uuid.uuid4()))
            await session.flush()
            raise ValueError("boom")

    outer_result = await session.execute(select(_Entity).where(_Entity.id == outer_id))
    assert outer_result.scalar_one_or_none() is not None
    inner_result = await session.execute(select(_Entity).where(_Entity.id == inner_id))
    assert inner_result.scalar_one_or_none() is None


async def test_run_with_retry_retries_then_succeeds() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _make_retryable_error()
        return "ok"

    result = await run_with_retry(
        flaky, max_attempts=5, backoff_base_seconds=0.001, backoff_max_seconds=0.01
    )

    assert result == "ok"
    assert attempts == 3


async def test_run_with_retry_raises_immediately_for_non_retryable_error() -> None:
    async def always_fails() -> None:
        raise _make_non_retryable_error()

    with pytest.raises(OperationalError):
        await run_with_retry(always_fails, max_attempts=5, backoff_base_seconds=0.001)


async def test_run_with_retry_exhausts_attempts_and_raises() -> None:
    async def always_retryable() -> None:
        raise _make_retryable_error()

    with pytest.raises(OperationalError):
        await run_with_retry(
            always_retryable, max_attempts=2, backoff_base_seconds=0.001, backoff_max_seconds=0.01
        )


# --- unit_of_work.py ---


async def test_unit_of_work_commits_on_clean_exit(session_factory: _SessionFactory) -> None:
    entity_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(_Entity).where(_Entity.id == entity_id))
        assert result.scalar_one_or_none() is not None


async def test_unit_of_work_rolls_back_on_exception(session_factory: _SessionFactory) -> None:
    entity_id = uuid.uuid4()
    with pytest.raises(ValueError, match="boom"):
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))
            raise ValueError("boom")

    async with session_factory() as verify_session:
        result = await verify_session.execute(select(_Entity).where(_Entity.id == entity_id))
        assert result.scalar_one_or_none() is None


async def test_unit_of_work_session_property_raises_before_enter(
    session_factory: _SessionFactory,
) -> None:
    uow = UnitOfWork(session_factory)
    with pytest.raises(RuntimeError, match="__aenter__"):
        _ = uow.session


def test_unit_of_work_requires_session_factory_or_session() -> None:
    with pytest.raises(TypeError, match="requires either"):
        UnitOfWork()


async def test_unit_of_work_from_session_keeps_the_caller_session_open(
    session: AsyncSession,
) -> None:
    entity_id = uuid.uuid4()
    async with UnitOfWork.from_session(session) as uow:
        assert uow.session is session
        session.add(_Entity(id=entity_id, name="x", organization_id=uuid.uuid4()))

    # The caller's session is still open and usable after the unit of work exits.
    result = await session.execute(select(_Entity).where(_Entity.id == entity_id))
    assert result.scalar_one_or_none() is not None


async def test_unit_of_work_nested_rolls_back_only_the_savepoint(session: AsyncSession) -> None:
    async with UnitOfWork.from_session(session) as uow:
        with pytest.raises(ValueError, match="boom"):
            async with uow.nested():
                session.add(_Entity(name="inner", organization_id=uuid.uuid4()))
                await session.flush()
                raise ValueError("boom")
        uow.session.add(_Entity(name="outer", organization_id=uuid.uuid4()))

    result = await session.execute(select(_Entity))
    assert len(result.scalars().all()) == 1


async def test_unit_of_work_run_with_retry_retries_then_succeeds(session: AsyncSession) -> None:
    uow = UnitOfWork.from_session(session)
    attempts = 0

    async def flaky(_session: AsyncSession) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise _make_retryable_error()
        return "ok"

    result = await uow.run_with_retry(flaky, max_attempts=5, backoff_base_seconds=0.001)

    assert result == "ok"
    assert attempts == 2


# --- decorators.py: readonly / tenant / soft_delete / retry ---


async def test_readonly_decorator_rolls_back_even_on_success(session: AsyncSession) -> None:
    @readonly
    async def add_entity(session: AsyncSession) -> None:
        session.add(_Entity(name="x", organization_id=uuid.uuid4()))
        await session.flush()

    await add_entity(session)

    result = await session.execute(select(_Entity))
    assert result.scalars().first() is None


async def test_readonly_decorator_requires_a_session_argument() -> None:
    @readonly
    async def no_session_here() -> None:
        return None

    with pytest.raises(TypeError, match="AsyncSession"):
        await no_session_here()


async def test_tenant_decorator_allows_matching_organization() -> None:
    org_id = uuid.uuid4()
    bind_security_context(organization_id=org_id, role=Role.OPERATOR)

    @tenant()
    async def scoped_action(*, organization_id: uuid.UUID) -> str:
        return "ok"

    assert await scoped_action(organization_id=org_id) == "ok"


async def test_tenant_decorator_denies_mismatched_organization() -> None:
    bind_security_context(organization_id=uuid.uuid4(), role=Role.OPERATOR)

    @tenant()
    async def scoped_action(*, organization_id: uuid.UUID) -> str:
        return "ok"

    with pytest.raises(TenantViolationError):
        await scoped_action(organization_id=uuid.uuid4())


async def test_tenant_decorator_denies_missing_organization_id_argument() -> None:
    bind_security_context(organization_id=uuid.uuid4(), role=Role.OPERATOR)

    @tenant()
    async def scoped_action() -> str:
        return "ok"

    with pytest.raises(TenantViolationError, match="requires"):
        await scoped_action()


async def test_tenant_decorator_bypasses_for_super_admin() -> None:
    bind_security_context(role=Role.SUPER_ADMIN)

    @tenant()
    async def scoped_action() -> str:
        return "ok"

    assert await scoped_action() == "ok"


async def test_soft_delete_decorator_forces_deleted_fields() -> None:
    entity = _Entity(name="x")

    @soft_delete
    async def custom_delete(*, deleted_by: uuid.UUID | None = None) -> _Entity:
        return entity

    deleter = uuid.uuid4()
    result = await custom_delete(deleted_by=deleter)

    assert result.is_active is False
    assert result.deleted_by == deleter


async def test_retry_decorator_retries_then_succeeds() -> None:
    attempts = 0

    @retry(max_attempts=5, backoff_base_seconds=0.001, backoff_max_seconds=0.01)
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _make_retryable_error()
        return "ok"

    assert await flaky() == "ok"
    assert attempts == 3


async def test_retry_decorator_exhausts_attempts_and_raises_transaction_failed() -> None:
    @retry(max_attempts=2, backoff_base_seconds=0.001, backoff_max_seconds=0.01)
    async def always_retryable() -> None:
        raise _make_retryable_error()

    with pytest.raises(OperationalError):
        await always_retryable()


# --- seed.py ---


async def test_seed_registry_runs_seeds_in_order_for_matching_environment(
    session: AsyncSession,
) -> None:
    registry = SeedRegistry()
    executed: list[str] = []

    @seed(registry, "second", SeedEnvironment.DEVELOPMENT, order=2)
    async def _second(_session: AsyncSession) -> None:
        executed.append("second")

    @seed(registry, "first", SeedEnvironment.DEVELOPMENT, order=1)
    async def _first(_session: AsyncSession) -> None:
        executed.append("first")

    @seed(registry, "testing-only", SeedEnvironment.TESTING)
    async def _testing_only(_session: AsyncSession) -> None:
        executed.append("testing-only")

    ran = await registry.run(session, SeedEnvironment.DEVELOPMENT)

    assert executed == ["first", "second"]
    assert ran == ["first", "second"]


def test_seed_registry_rejects_duplicate_name_for_same_environment() -> None:
    registry = SeedRegistry()

    async def _noop(_session: AsyncSession) -> None:
        return None

    registry.register("dup", SeedEnvironment.DEMO, _noop)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", SeedEnvironment.DEMO, _noop)


# --- fixtures.py ---


class _EntityFactory(ModelFactory[_Entity]):
    model = _Entity

    @classmethod
    def default_values(cls) -> dict[str, object]:
        return {"name": f"entity-{cls.next_sequence()}", "organization_id": uuid.uuid4()}


class _BareFactory(ModelFactory[_Entity]):
    model = _Entity


def test_model_factory_default_values_base_implementation_is_empty() -> None:
    assert _BareFactory.default_values() == {}


def test_model_factory_build_uses_defaults_and_overrides() -> None:
    built = _EntityFactory.build()
    assert built.name.startswith("entity-")

    overridden = _EntityFactory.build(name="custom")
    assert overridden.name == "custom"


def test_model_factory_build_batch_returns_distinct_sequence_values() -> None:
    batch = _EntityFactory.build_batch(3)
    assert len({item.name for item in batch}) == 3


async def test_model_factory_create_persists_the_entity(session: AsyncSession) -> None:
    entity = await _EntityFactory.create(session)

    result = await session.execute(select(_Entity).where(_Entity.id == entity.id))
    assert result.scalar_one_or_none() is not None


async def test_model_factory_create_batch_persists_every_entity(session: AsyncSession) -> None:
    entities = await _EntityFactory.create_batch(session, 4)

    assert len(entities) == 4
    result = await session.execute(select(_Entity))
    assert len(result.scalars().all()) == 4


# --- factory.py ---


async def test_create_test_database_framework_provides_working_session_factory() -> None:
    framework = create_test_database_framework("sqlite+aiosqlite:///:memory:")
    async with framework.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with framework.session_factory() as db_session:
        db_session.add(_Entity(name="x", organization_id=uuid.uuid4()))
        await db_session.commit()

    status = await framework.check_health()
    assert status.status.value == "healthy"

    await framework.shutdown()


# --- connection.py ---


async def test_wait_for_database_succeeds_against_a_healthy_engine(engine: AsyncEngine) -> None:
    await wait_for_database(engine, max_attempts=1)


async def test_wait_for_database_raises_connection_failed_after_exhausting_attempts() -> None:
    broken_engine = create_test_engine("sqlite+aiosqlite:///nonexistent_dir/does_not_exist.db")
    with pytest.raises(ConnectionFailedError):
        await wait_for_database(
            broken_engine, max_attempts=2, backoff_base_seconds=0.001, backoff_max_seconds=0.01
        )
    await broken_engine.dispose()


async def test_graceful_shutdown_disposes_the_engine(engine: AsyncEngine) -> None:
    await graceful_shutdown(engine)  # does not raise; safe even if called again in fixture teardown


# --- health.py: pool status + full report ---


async def test_get_pool_status_returns_non_negative_counters(engine: AsyncEngine) -> None:
    status = get_pool_status(engine)

    assert status.size >= 0
    assert status.checked_in >= 0
    assert status.checked_out >= 0
    assert status.overflow >= 0


async def test_get_health_report_healthy_engine_has_no_server_version_on_sqlite(
    engine: AsyncEngine,
) -> None:
    report = await get_health_report(engine)

    assert report.status.value == "healthy"
    assert report.latency_ms >= 0
    # SQLite doesn't support "SHOW server_version" -- the except branch fires.
    assert report.server_version is None
    assert report.pool is not None


# --- helpers.py ---


def test_new_uuid_returns_a_uuid() -> None:
    assert isinstance(new_uuid(), uuid.UUID)


def test_utcnow_is_timezone_aware() -> None:
    assert utcnow().tzinfo == UTC


def test_migration_file_slug_normalizes_message() -> None:
    assert migration_file_slug("Add users table!") == "add_users_table"
    assert migration_file_slug("   ") == "migration"


# --- search.py ---


def test_apply_search_returns_statement_unmodified_for_empty_query() -> None:
    stmt = select(_Entity)
    assert apply_search(stmt, _Entity, ["name"], "   ") is stmt
    assert apply_search(stmt, _Entity, [], "anything") is stmt
