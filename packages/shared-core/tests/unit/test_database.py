"""Tests for the generic repository, transaction manager, and health check."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from shared_core.base import BaseEntityMixin
from shared_core.database import (
    Base,
    BaseRepository,
    Filter,
    FilterOperator,
    SortDirection,
    SortField,
    VersionConflictError,
    check_database_health,
    create_session_factory,
    create_test_engine,
)
from shared_core.database.transaction import unit_of_work
from shared_core.enums import HealthStatus
from shared_core.exceptions import NotFoundError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class _Widget(Base, BaseEntityMixin):
    __tablename__ = "widgets"

    name: Mapped[str] = mapped_column()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_test_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


@pytest.fixture
def repository(session: AsyncSession) -> BaseRepository[_Widget]:
    return BaseRepository(session, _Widget)


async def test_create_and_get_by_id(repository: BaseRepository[_Widget]) -> None:
    widget = _Widget(name="thing", organization_id=uuid.uuid4())

    created = await repository.create(widget)
    fetched = await repository.get_by_id(created.id)

    assert fetched is not None
    assert fetched.name == "thing"


async def test_find_by_id_and_find_by_uuid_are_aliases_of_get_by_id(
    repository: BaseRepository[_Widget],
) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    assert (await repository.find_by_id(widget.id)) is not None
    assert (await repository.find_by_uuid(widget.id)) is not None


async def test_get_by_id_returns_none_for_missing_entity(
    repository: BaseRepository[_Widget],
) -> None:
    assert await repository.get_by_id(uuid.uuid4()) is None


async def test_require_by_id_raises_not_found_for_missing_entity(
    repository: BaseRepository[_Widget],
) -> None:
    with pytest.raises(NotFoundError):
        await repository.require_by_id(uuid.uuid4())


async def test_require_by_id_returns_entity_when_present(
    repository: BaseRepository[_Widget],
) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    found = await repository.require_by_id(widget.id)

    assert found.id == widget.id


async def test_exists_reflects_active_entities_only(repository: BaseRepository[_Widget]) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    assert await repository.exists(widget.id) is True

    await repository.delete(widget.id)

    assert await repository.exists(widget.id) is False


async def test_delete_soft_deletes_and_sets_deleted_by(repository: BaseRepository[_Widget]) -> None:
    deleter_id = uuid.uuid4()
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    await repository.delete(widget.id, deleted_by=deleter_id)

    deleted = await repository.get_by_id(widget.id, include_deleted=True)
    assert deleted is not None
    assert deleted.is_active is False
    assert deleted.deleted_by == deleter_id
    assert deleted.deleted_at is not None


async def test_delete_raises_not_found_for_missing_entity(
    repository: BaseRepository[_Widget],
) -> None:
    with pytest.raises(NotFoundError):
        await repository.delete(uuid.uuid4())


async def test_restore_reactivates_a_soft_deleted_entity(
    repository: BaseRepository[_Widget],
) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))
    await repository.delete(widget.id)

    restored = await repository.restore(widget.id)

    assert restored.is_active is True
    assert restored.deleted_at is None
    assert await repository.exists(widget.id) is True


async def test_restore_raises_not_found_for_missing_entity(
    repository: BaseRepository[_Widget],
) -> None:
    with pytest.raises(NotFoundError):
        await repository.restore(uuid.uuid4())


async def test_purge_permanently_removes_the_row(repository: BaseRepository[_Widget]) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    await repository.purge(widget.id)

    assert await repository.get_by_id(widget.id, include_deleted=True) is None


async def test_purge_raises_not_found_for_missing_entity(
    repository: BaseRepository[_Widget],
) -> None:
    with pytest.raises(NotFoundError):
        await repository.purge(uuid.uuid4())


async def test_update_increments_version(repository: BaseRepository[_Widget]) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))
    assert widget.version == 1

    updated = await repository.update(widget)

    assert updated.version == 2


async def test_update_with_matching_expected_version_succeeds(
    repository: BaseRepository[_Widget],
) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    updated = await repository.update(widget, expected_version=1)

    assert updated.version == 2


async def test_update_with_stale_expected_version_raises_version_conflict(
    repository: BaseRepository[_Widget],
) -> None:
    widget = await repository.create(_Widget(name="thing", organization_id=uuid.uuid4()))

    with pytest.raises(VersionConflictError):
        await repository.update(widget, expected_version=99)


async def test_count_matches_active_entities_with_filter(
    repository: BaseRepository[_Widget],
) -> None:
    org_id = uuid.uuid4()
    await repository.create(_Widget(name="a", organization_id=org_id))
    await repository.create(_Widget(name="b", organization_id=org_id))
    await repository.create(_Widget(name="c", organization_id=uuid.uuid4()))

    assert await repository.count(organization_id=org_id) == 2


async def test_bulk_create_persists_every_entity(repository: BaseRepository[_Widget]) -> None:
    org_id = uuid.uuid4()
    widgets = [_Widget(name=f"w{i}", organization_id=org_id) for i in range(3)]

    created = await repository.bulk_create(widgets)

    assert len(created) == 3
    assert await repository.count(organization_id=org_id) == 3


async def test_bulk_update_increments_version_on_every_entity(
    repository: BaseRepository[_Widget],
) -> None:
    org_id = uuid.uuid4()
    widgets = await repository.bulk_create(
        [_Widget(name=f"w{i}", organization_id=org_id) for i in range(3)]
    )

    updated = await repository.bulk_update(widgets)

    assert all(w.version == 2 for w in updated)


async def test_bulk_delete_soft_deletes_the_given_ids_and_returns_the_count(
    repository: BaseRepository[_Widget],
) -> None:
    org_id = uuid.uuid4()
    widgets = await repository.bulk_create(
        [_Widget(name=f"w{i}", organization_id=org_id) for i in range(3)]
    )

    affected = await repository.bulk_delete([w.id for w in widgets[:2]])

    assert affected == 2
    assert await repository.count(organization_id=org_id) == 1


async def test_bulk_delete_with_no_ids_returns_zero(repository: BaseRepository[_Widget]) -> None:
    assert await repository.bulk_delete([]) == 0


async def test_search_matches_ilike_across_fields(repository: BaseRepository[_Widget]) -> None:
    org_id = uuid.uuid4()
    await repository.create(_Widget(name="Blue Widget", organization_id=org_id))
    await repository.create(_Widget(name="Red Gadget", organization_id=org_id))

    results = await repository.search(["name"], "widget")

    assert len(results) == 1
    assert results[0].name == "Blue Widget"


async def test_paginate_returns_metadata_and_items(repository: BaseRepository[_Widget]) -> None:
    org_id = uuid.uuid4()
    for i in range(5):
        await repository.create(_Widget(name=f"w{i}", organization_id=org_id))

    page = await repository.paginate(page=1, page_size=2)

    assert len(page.items) == 2
    assert page.metadata.total == 5
    assert page.metadata.has_next is True
    assert page.metadata.has_previous is False


async def test_paginate_applies_filters_and_sort_fields(
    repository: BaseRepository[_Widget],
) -> None:
    org_id = uuid.uuid4()
    for i in range(5):
        await repository.create(_Widget(name=f"w{i}", organization_id=org_id))

    page = await repository.paginate(
        filters=[Filter("name", FilterOperator.CONTAINS, "w")],
        sort_fields=[SortField("name", SortDirection.DESC)],
    )

    assert page.metadata.total == 5
    assert [item.name for item in page.items] == ["w4", "w3", "w2", "w1", "w0"]


async def test_unit_of_work_commits_on_success(session: AsyncSession) -> None:
    widget_id = uuid.uuid4()
    async with unit_of_work(session):
        session.add(_Widget(id=widget_id, name="thing", organization_id=uuid.uuid4()))

    repository = BaseRepository(session, _Widget)
    assert await repository.exists(widget_id) is True


async def test_unit_of_work_rolls_back_on_error(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="boom"):
        async with unit_of_work(session):
            session.add(_Widget(name="thing", organization_id=uuid.uuid4()))
            raise ValueError("boom")

    result = await session.execute(_Widget.__table__.select())
    assert result.first() is None


async def test_check_database_health_reports_healthy_for_working_engine(
    engine: AsyncEngine,
) -> None:
    status, latency_ms = await check_database_health(engine)

    assert status == HealthStatus.HEALTHY
    assert latency_ms >= 0


async def test_check_database_health_reports_unhealthy_for_broken_engine() -> None:
    broken_engine = create_test_engine("sqlite+aiosqlite:///nonexistent_dir/does_not_exist.db")

    status, _ = await check_database_health(broken_engine)

    assert status == HealthStatus.UNHEALTHY
    await broken_engine.dispose()
