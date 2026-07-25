"""Integration tests against the real docker-compose PostgreSQL instance.

Everything here exercises behavior that cannot be verified against SQLite:
PostgreSQL-specific SQLSTATE-driven exception mapping, JSONB filtering,
full-text/trigram search, tenant isolation end-to-end, and the Alembic
migration framework. Skips (rather than fails) if Postgres is unreachable,
per this file's ``pg_engine``/``pg_session`` fixtures.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from shared_core.base import BaseEntityMixin
from shared_core.database.exceptions import (
    ConstraintFailedError,
    DuplicateRecordError,
    TenantViolationError,
)
from shared_core.database.factory import create_database_framework
from shared_core.database.filtering import Filter, FilterOperator, apply_filters
from shared_core.database.migration import (
    build_alembic_config,
    downgrade,
    generate_revision,
    get_current_revision_async,
    get_head_revision,
    get_migration_history,
    get_migration_status,
    upgrade,
    validate_migrations,
)
from shared_core.database.repository import BaseRepository
from shared_core.database.search import SearchMode
from shared_core.database.session import create_session_factory
from shared_core.database.tenant import TenantScope
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tests.unit.conftest import postgres_test_settings


class _PgBase(DeclarativeBase):
    """A private declarative base for this file's PostgreSQL-only-typed model.

    Deliberately NOT :class:`shared_core.database.base.Base` -- that base's
    metadata is shared with every SQLite-backed test in this package, and a
    JSONB column can't be rendered by SQLite's DDL compiler. Isolating this
    model onto its own base keeps ``Base.metadata.create_all()`` calls
    elsewhere in the suite from ever seeing it.
    """


class _PgEntity(_PgBase, BaseEntityMixin):
    __tablename__ = "dbfw_test_entities"

    sku: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(default="")
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)


@pytest.fixture
async def pg_session_factory(
    pg_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with pg_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(_PgBase.metadata.create_all, tables=[_PgEntity.__table__])
    yield create_session_factory(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.run_sync(_PgBase.metadata.drop_all, tables=[_PgEntity.__table__])


@pytest.fixture
async def pg_session(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with pg_session_factory() as session:
        yield session
        await session.rollback()


def _entity(**overrides: object) -> _PgEntity:
    values: dict[str, object] = {
        "sku": f"sku-{uuid.uuid4()}",
        "description": "",
        "organization_id": uuid.uuid4(),
    }
    values.update(overrides)
    return _PgEntity(**values)  # type: ignore[arg-type]


# --- Constraint / duplicate-key mapping ---


async def test_create_duplicate_sku_raises_duplicate_record_error(
    pg_session: AsyncSession,
) -> None:
    repository = BaseRepository(pg_session, _PgEntity)
    sku = f"sku-{uuid.uuid4()}"
    await repository.create(_entity(sku=sku))

    with pytest.raises(DuplicateRecordError):
        await repository.create(_entity(sku=sku))


async def test_create_null_sku_raises_constraint_failed_error(pg_session: AsyncSession) -> None:
    repository = BaseRepository(pg_session, _PgEntity)

    with pytest.raises(ConstraintFailedError):
        await repository.create(_entity(sku=None))


async def test_update_to_duplicate_sku_raises_duplicate_record_error(
    pg_session: AsyncSession,
) -> None:
    repository = BaseRepository(pg_session, _PgEntity)
    taken_sku = f"sku-{uuid.uuid4()}"
    await repository.create(_entity(sku=taken_sku))
    other = await repository.create(_entity())

    other.sku = taken_sku
    with pytest.raises(DuplicateRecordError):
        await repository.update(other)


async def test_bulk_create_duplicate_sku_raises_duplicate_record_error(
    pg_session: AsyncSession,
) -> None:
    repository = BaseRepository(pg_session, _PgEntity)
    taken_sku = f"sku-{uuid.uuid4()}"
    await repository.create(_entity(sku=taken_sku))

    with pytest.raises(DuplicateRecordError):
        await repository.bulk_create([_entity(sku=taken_sku)])


async def test_bulk_update_to_duplicate_sku_raises_duplicate_record_error(
    pg_session: AsyncSession,
) -> None:
    repository = BaseRepository(pg_session, _PgEntity)
    taken_sku = f"sku-{uuid.uuid4()}"
    await repository.create(_entity(sku=taken_sku))
    other = await repository.create(_entity())

    other.sku = taken_sku
    with pytest.raises(DuplicateRecordError):
        await repository.bulk_update([other])


# --- JSONB filtering ---


async def test_jsonb_contains_and_has_key_filters(pg_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    repository = BaseRepository(pg_session, _PgEntity)
    blue_attrs = {"color": "blue", "size": "m"}
    await repository.create(_entity(organization_id=org_id, attributes=blue_attrs))
    await repository.create(_entity(organization_id=org_id, attributes={"color": "red"}))

    stmt = apply_filters(
        select(_PgEntity),
        _PgEntity,
        [Filter("attributes", FilterOperator.JSONB_CONTAINS, {"color": "blue"})],
    )
    results = (await pg_session.execute(stmt)).scalars().all()
    assert len(results) == 1
    assert results[0].attributes["color"] == "blue"

    stmt = apply_filters(
        select(_PgEntity), _PgEntity, [Filter("attributes", FilterOperator.JSONB_HAS_KEY, "size")]
    )
    results = (await pg_session.execute(stmt)).scalars().all()
    assert len(results) == 1
    assert results[0].attributes["size"] == "m"


# --- Search ---


async def test_full_text_search_matches_natural_language_query(pg_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    repository = BaseRepository(pg_session, _PgEntity)
    await repository.create(_entity(organization_id=org_id, description="a fast red sports car"))
    await repository.create(_entity(organization_id=org_id, description="a slow blue bicycle"))

    results = await repository.search(["description"], "red car", mode=SearchMode.FULL_TEXT)

    assert len(results) == 1
    assert "red" in results[0].description


async def test_trigram_search_tolerates_typos(pg_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    repository = BaseRepository(pg_session, _PgEntity)
    await repository.create(_entity(organization_id=org_id, description="widget"))
    await repository.create(_entity(organization_id=org_id, description="unrelated gadget"))

    results = await repository.search(["description"], "widgt", mode=SearchMode.TRIGRAM)

    assert any(r.description == "widget" for r in results)


# --- Tenant isolation ---


async def test_repository_with_tenant_scope_only_sees_its_own_organization(
    pg_session: AsyncSession,
) -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    repository = BaseRepository(pg_session, _PgEntity)
    entity_a = await repository.create(_entity(organization_id=org_a))
    entity_b = await repository.create(_entity(organization_id=org_b))

    scoped = BaseRepository(pg_session, _PgEntity, tenant_scope=TenantScope(organization_id=org_a))

    assert await scoped.get_by_id(entity_a.id) is not None
    assert await scoped.get_by_id(entity_b.id) is None
    assert await scoped.count() == 1


async def test_repository_tenant_scope_without_organization_id_raises_on_query(
    pg_session: AsyncSession,
) -> None:
    scoped = BaseRepository(
        pg_session, _PgEntity, tenant_scope=TenantScope(organization_id=None, is_super_admin=False)
    )

    with pytest.raises(TenantViolationError):
        await scoped.count()


async def test_repository_super_admin_tenant_scope_sees_every_organization(
    pg_session: AsyncSession,
) -> None:
    repository = BaseRepository(pg_session, _PgEntity)
    await repository.create(_entity(organization_id=uuid.uuid4()))
    await repository.create(_entity(organization_id=uuid.uuid4()))

    super_scope = BaseRepository(
        pg_session, _PgEntity, tenant_scope=TenantScope(organization_id=None, is_super_admin=True)
    )
    assert await super_scope.count() >= 2


# --- Migration framework ---


_ENV_PY = """
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = None


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""

_SCRIPT_MAKO = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''

_REVISION_TEMPLATE = '''"""create migration test table

Revision ID: {revision}
Revises:
Create Date: 2026-01-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = {revision!r}
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dbfw_migration_test",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.String(length=50), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dbfw_migration_test")
'''


def _write_alembic_project(script_location: Path) -> None:
    script_location.mkdir(parents=True, exist_ok=True)
    (script_location / "env.py").write_text(_ENV_PY, encoding="utf-8")
    (script_location / "script.py.mako").write_text(_SCRIPT_MAKO, encoding="utf-8")
    (script_location / "versions").mkdir(exist_ok=True)


# --- factory.py / health.py: real PostgreSQL engine ---


async def test_create_database_framework_reports_real_server_version(
    pg_engine: AsyncEngine,
) -> None:
    del pg_engine  # only used to trigger the "skip if unreachable" fixture check
    framework = await create_database_framework(postgres_test_settings(), wait_for_ready=True)
    try:
        report = await framework.check_health()
        assert report.status.value == "healthy"
        assert report.server_version is not None
    finally:
        await framework.shutdown()


async def test_migration_generate_upgrade_downgrade_and_status(
    tmp_path: Path, pg_engine: AsyncEngine
) -> None:
    script_location = tmp_path / "migrations"
    _write_alembic_project(script_location)
    dsn = pg_engine.url.render_as_string(hide_password=False)
    config = build_alembic_config(script_location=script_location, dsn=dsn)
    config.set_main_option("version_table", "dbfw_test_alembic_version")

    # No revisions yet: nothing to validate, no head, no history.
    validate_migrations(config)  # should not raise with zero heads
    assert get_head_revision(config) is None
    assert get_migration_history(config) == []

    # A no-op autogenerate=False revision is created but does nothing on upgrade.
    stub_revision = generate_revision(config, "empty stub", autogenerate=False)
    assert stub_revision is not None
    assert get_head_revision(config) == stub_revision

    # Replace the stub with a hand-written revision that actually creates a table.
    revision_id = "dbfw0001"
    for stub_file in (script_location / "versions").glob("*.py"):
        stub_file.unlink()
    (script_location / "versions" / f"{revision_id}_create_table.py").write_text(
        _REVISION_TEMPLATE.format(revision=revision_id), encoding="utf-8"
    )

    assert get_head_revision(config) == revision_id
    assert get_migration_history(config) == [revision_id]
    validate_migrations(config)  # single head: still fine

    try:
        upgrade(config, "head")
        current = await get_current_revision_async(pg_engine)
        assert current == revision_id

        status = await get_migration_status(pg_engine, config)
        assert status.current_revision == revision_id
        assert status.head_revision == revision_id
        assert status.is_up_to_date is True

        async with pg_engine.connect() as conn:
            result = await conn.execute(text("SELECT to_regclass('dbfw_migration_test')"))
            assert result.scalar_one() is not None

        downgrade(config, "base")
        current_after_downgrade = await get_current_revision_async(pg_engine)
        assert current_after_downgrade is None

        async with pg_engine.connect() as conn:
            result = await conn.execute(text("SELECT to_regclass('dbfw_migration_test')"))
            assert result.scalar_one() is None
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS dbfw_migration_test"))
            await conn.execute(text("DROP TABLE IF EXISTS dbfw_test_alembic_version"))
