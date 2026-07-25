"""Tests for filtering, sorting, pagination, and the query builder."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.base import BaseEntityMixin
from shared_core.database import (
    Base,
    Filter,
    FilterOperator,
    NullsPosition,
    PaginationMetadata,
    QueryBuilder,
    SortDirection,
    SortField,
    apply_filters,
    apply_sorting,
    create_session_factory,
    create_test_engine,
    decode_cursor,
    encode_cursor,
    paginate_by_cursor,
    paginate_by_offset,
    parse_sort_expression,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class _Item(Base, BaseEntityMixin):
    __tablename__ = "query_test_items"

    name: Mapped[str] = mapped_column()
    priority: Mapped[int] = mapped_column(default=0)
    tag: Mapped[str | None] = mapped_column(default=None)


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


async def _seed_items(
    session: AsyncSession, count: int, *, org_id: uuid.UUID | None = None
) -> list[_Item]:
    org_id = org_id or uuid.uuid4()
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    items = []
    for i in range(count):
        item = _Item(
            name=f"item-{i}",
            priority=i,
            tag="even" if i % 2 == 0 else None,
            organization_id=org_id,
        )
        item.created_at = base_time + timedelta(seconds=i)
        items.append(item)
    session.add_all(items)
    await session.flush()
    return items


# --- Filtering ---


async def test_filter_equal_and_not_equal(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    stmt = apply_filters(select(_Item), _Item, [Filter("priority", FilterOperator.EQUAL, 2)])
    result = (await session.execute(stmt)).scalars().all()
    assert [r.priority for r in result] == [2]

    stmt = apply_filters(select(_Item), _Item, [Filter("priority", FilterOperator.NOT_EQUAL, 2)])
    result = (await session.execute(stmt)).scalars().all()
    assert 2 not in [r.priority for r in result]


async def test_filter_comparisons_and_between(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    stmt = apply_filters(select(_Item), _Item, [Filter("priority", FilterOperator.GREATER_THAN, 2)])
    assert {r.priority for r in (await session.execute(stmt)).scalars().all()} == {3, 4}

    stmt = apply_filters(select(_Item), _Item, [Filter("priority", FilterOperator.LESS_THAN, 2)])
    assert {r.priority for r in (await session.execute(stmt)).scalars().all()} == {0, 1}

    stmt = apply_filters(
        select(_Item), _Item, [Filter("priority", FilterOperator.BETWEEN, value=1, value2=3)]
    )
    assert {r.priority for r in (await session.execute(stmt)).scalars().all()} == {1, 2, 3}


async def test_filter_contains_starts_with_ends_with(session: AsyncSession) -> None:
    await _seed_items(session, 3)

    stmt = apply_filters(select(_Item), _Item, [Filter("name", FilterOperator.CONTAINS, "tem-1")])
    assert [r.name for r in (await session.execute(stmt)).scalars().all()] == ["item-1"]

    stmt = apply_filters(select(_Item), _Item, [Filter("name", FilterOperator.STARTS_WITH, "item")])
    assert len((await session.execute(stmt)).scalars().all()) == 3

    stmt = apply_filters(select(_Item), _Item, [Filter("name", FilterOperator.ENDS_WITH, "m-2")])
    assert [r.name for r in (await session.execute(stmt)).scalars().all()] == ["item-2"]


async def test_filter_null_and_not_null(session: AsyncSession) -> None:
    await _seed_items(session, 4)

    stmt = apply_filters(select(_Item), _Item, [Filter("tag", FilterOperator.IS_NULL)])
    assert {r.priority for r in (await session.execute(stmt)).scalars().all()} == {1, 3}

    stmt = apply_filters(select(_Item), _Item, [Filter("tag", FilterOperator.IS_NOT_NULL)])
    assert {r.priority for r in (await session.execute(stmt)).scalars().all()} == {0, 2}


async def test_filter_boolean_true_and_false(session: AsyncSession) -> None:
    items = await _seed_items(session, 2)
    items[0].is_active = False
    await session.flush()

    stmt = apply_filters(select(_Item), _Item, [Filter("is_active", FilterOperator.IS_FALSE)])
    assert len((await session.execute(stmt)).scalars().all()) == 1

    stmt = apply_filters(select(_Item), _Item, [Filter("is_active", FilterOperator.IS_TRUE)])
    assert len((await session.execute(stmt)).scalars().all()) == 1


async def test_filter_date_range(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    low = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
    high = datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC)
    date_filter = Filter("created_at", FilterOperator.DATE_RANGE, value=low, value2=high)
    stmt = apply_filters(select(_Item), _Item, [date_filter])
    assert {r.priority for r in (await session.execute(stmt)).scalars().all()} == {1, 2, 3}


def test_filter_requires_value_for_non_nullary_operators() -> None:
    with pytest.raises(ValueError, match="requires a value"):
        Filter("priority", FilterOperator.EQUAL)


def test_filter_requires_value2_for_range_operators() -> None:
    with pytest.raises(ValueError, match="requires both value"):
        Filter("priority", FilterOperator.BETWEEN, value=1)


def test_filter_nullary_operator_needs_no_value() -> None:
    assert Filter("tag", FilterOperator.IS_NULL).value is None


# --- Sorting ---


async def test_apply_sorting_ascending_and_descending(session: AsyncSession) -> None:
    await _seed_items(session, 3)

    asc_stmt = apply_sorting(select(_Item), _Item, [SortField("priority", SortDirection.ASC)])
    assert [r.priority for r in (await session.execute(asc_stmt)).scalars().all()] == [0, 1, 2]

    desc_stmt = apply_sorting(select(_Item), _Item, [SortField("priority", SortDirection.DESC)])
    assert [r.priority for r in (await session.execute(desc_stmt)).scalars().all()] == [2, 1, 0]


async def test_apply_sorting_multiple_fields(session: AsyncSession) -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    session.add_all(
        [
            _Item(name="x", priority=1, organization_id=org_b),
            _Item(name="y", priority=1, organization_id=org_a),
            _Item(name="z", priority=0, organization_id=org_a),
        ]
    )
    await session.flush()

    stmt = apply_sorting(
        select(_Item),
        _Item,
        [SortField("priority", SortDirection.ASC), SortField("organization_id", SortDirection.ASC)],
    )
    result = (await session.execute(stmt)).scalars().all()
    assert [r.priority for r in result] == [0, 1, 1]


async def test_apply_sorting_nulls_first_and_last(session: AsyncSession) -> None:
    await _seed_items(session, 4)

    stmt = apply_sorting(select(_Item), _Item, [SortField("tag", nulls=NullsPosition.FIRST)])
    result = (await session.execute(stmt)).scalars().all()
    assert result[0].tag is None

    stmt = apply_sorting(select(_Item), _Item, [SortField("tag", nulls=NullsPosition.LAST)])
    result = (await session.execute(stmt)).scalars().all()
    assert result[-1].tag is None


def test_parse_sort_expression() -> None:
    fields = parse_sort_expression("created_at:desc:nulls_last,name:asc")
    assert fields == [
        SortField("created_at", SortDirection.DESC, NullsPosition.LAST),
        SortField("name", SortDirection.ASC, None),
    ]


def test_parse_sort_expression_empty_returns_empty_list() -> None:
    assert parse_sort_expression(None) == []
    assert parse_sort_expression("") == []


def test_parse_sort_expression_bare_field_defaults_ascending() -> None:
    assert parse_sort_expression("name") == [SortField("name", SortDirection.ASC, None)]


def test_parse_sort_expression_supports_nulls_first() -> None:
    fields = parse_sort_expression("tag:asc:nulls_first")
    assert fields == [SortField("tag", SortDirection.ASC, NullsPosition.FIRST)]


def test_parse_sort_expression_skips_empty_terms() -> None:
    fields = parse_sort_expression("name:asc,,priority:desc")
    assert fields == [
        SortField("name", SortDirection.ASC, None),
        SortField("priority", SortDirection.DESC, None),
    ]


# --- Pagination ---


async def test_paginate_by_offset_metadata(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    page = await paginate_by_offset(session, select(_Item), page=2, page_size=2)

    assert len(page.items) == 2
    assert page.metadata.total == 5
    assert page.metadata.page == 2
    assert page.metadata.has_next is True
    assert page.metadata.has_previous is True
    assert page.metadata.total_pages == 3


async def test_paginate_by_offset_last_page_has_no_next(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    page = await paginate_by_offset(session, select(_Item), page=3, page_size=2)

    assert len(page.items) == 1
    assert page.metadata.has_next is False


def test_pagination_metadata_total_pages_is_zero_for_non_positive_page_size() -> None:
    metadata = PaginationMetadata(total=10, page=1, page_size=0, has_next=False, has_previous=False)
    assert metadata.total_pages == 0


def test_encode_and_decode_cursor_round_trips() -> None:
    value = datetime(2026, 1, 1, tzinfo=UTC)
    entity_id = uuid.uuid4()

    cursor = encode_cursor(value, entity_id)
    decoded_value, decoded_id = decode_cursor(cursor)

    assert decoded_value == value
    assert decoded_id == entity_id


def test_decode_cursor_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="Invalid pagination cursor"):
        decode_cursor("not-a-valid-cursor!!")


async def test_paginate_by_cursor_walks_every_page_in_order(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    seen: list[int] = []
    cursor: str | None = None
    for _ in range(10):
        page = await paginate_by_cursor(session, select(_Item), _Item, cursor=cursor, limit=2)
        seen.extend(item.priority for item in page.items)
        if not page.has_next:
            break
        cursor = page.next_cursor

    assert seen == [0, 1, 2, 3, 4]


# --- Query Builder ---


async def test_query_builder_where_and_where_in(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    builder = QueryBuilder(_Item).where_in("priority", [1, 3])
    results = await builder.all(session)

    assert {r.priority for r in results} == {1, 3}


async def test_query_builder_where_any_and_where_not(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    builder = QueryBuilder(_Item).where_any(_Item.priority == 0, _Item.priority == 4)
    results = await builder.all(session)
    assert {r.priority for r in results} == {0, 4}

    builder = QueryBuilder(_Item).where_not(_Item.priority == 0)
    results = await builder.all(session)
    assert 0 not in {r.priority for r in results}


async def test_query_builder_where_between_and_like(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    builder = QueryBuilder(_Item).where_between("priority", 1, 3)
    assert {r.priority for r in await builder.all(session)} == {1, 2, 3}

    builder = QueryBuilder(_Item).like("name", "%item-2%")
    assert [r.priority for r in await builder.all(session)] == [2]


async def test_query_builder_filters_and_search(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    builder = QueryBuilder(_Item).filters([Filter("priority", FilterOperator.GREATER_THAN, 2)])
    assert {r.priority for r in await builder.all(session)} == {3, 4}

    builder = QueryBuilder(_Item).search(["name"], "item-1")
    assert [r.priority for r in await builder.all(session)] == [1]


async def test_query_builder_order_by_limit_offset(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    builder = (
        QueryBuilder(_Item).order_by([SortField("priority", SortDirection.DESC)]).limit(2).offset(1)
    )
    results = await builder.all(session)

    assert [r.priority for r in results] == [3, 2]


async def test_query_builder_count_and_first(session: AsyncSession) -> None:
    await _seed_items(session, 3)

    builder = QueryBuilder(_Item)
    assert await builder.count(session) == 3

    ordered = QueryBuilder(_Item).order_by([SortField("priority", SortDirection.ASC)])
    first = await ordered.first(session)
    assert first is not None
    assert first.priority == 0


async def test_query_builder_first_returns_none_when_no_match(session: AsyncSession) -> None:
    builder = QueryBuilder(_Item).where(_Item.priority == 999)
    assert await builder.first(session) is None


async def test_query_builder_group_by_and_aggregate(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    aggregate_stmt = QueryBuilder(_Item).aggregate("priority", agg="max")
    result = await session.execute(aggregate_stmt)
    assert result.scalar_one() == 4

    grouped = QueryBuilder(_Item).group_by("tag").statement
    rows = (await session.execute(grouped)).all()
    assert len(rows) == 2  # "even" and NULL


async def test_query_builder_paginate(session: AsyncSession) -> None:
    await _seed_items(session, 5)

    page = await QueryBuilder(_Item).paginate(session, page=1, page_size=3)

    assert len(page.items) == 3
    assert page.metadata.total == 5


async def test_query_builder_exists_clause_and_subquery(session: AsyncSession) -> None:
    await _seed_items(session, 3)

    inner = QueryBuilder(_Item).where(_Item.priority == 1)
    outer_stmt = select(_Item).where(inner.exists_clause())
    results = (await session.execute(outer_stmt)).scalars().all()
    assert len(results) == 3  # exists() with no correlation matches every outer row

    subquery = QueryBuilder(_Item).where(_Item.priority == 2).subquery()
    assert subquery is not None
