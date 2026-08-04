"""The organization-configurable catalogue repositories, against real PostgreSQL."""

from __future__ import annotations

import pytest

from app.models.enums import IncidentPriority, IncidentStatus
from app.models.incident import IncidentCategoryRecord, IncidentPriorityRecord, IncidentStatusRecord
from app.repositories.catalogue import (
    IncidentCategoryRepository,
    IncidentPriorityRepository,
    IncidentStatusRepository,
)

pytestmark = pytest.mark.asyncio


class TestIncidentCategoryRepository:
    async def test_get_by_slug_finds_a_created_category(
        self, categories_repo: IncidentCategoryRepository, organization_id
    ) -> None:
        created = await categories_repo.create(
            IncidentCategoryRecord(organization_id=organization_id, slug="db", name="Database")
        )
        found = await categories_repo.get_by_slug(organization_id, "db")
        assert found is not None
        assert found.id == created.id

    async def test_get_by_slug_is_none_when_missing(
        self, categories_repo: IncidentCategoryRepository, organization_id
    ) -> None:
        assert await categories_repo.get_by_slug(organization_id, "nope") is None

    async def test_list_for_org_orders_by_display_order_then_name(
        self, categories_repo: IncidentCategoryRepository, organization_id
    ) -> None:
        await categories_repo.create(
            IncidentCategoryRecord(
                organization_id=organization_id, slug="b", name="B", display_order=1
            )
        )
        await categories_repo.create(
            IncidentCategoryRecord(
                organization_id=organization_id, slug="a", name="A", display_order=0
            )
        )
        listed = await categories_repo.list_for_org(organization_id)
        assert [one.slug for one in listed] == ["a", "b"]


class TestIncidentPriorityRepository:
    async def test_get_for_priority_finds_an_override(
        self, priorities_repo: IncidentPriorityRepository, organization_id
    ) -> None:
        await priorities_repo.create(
            IncidentPriorityRecord(
                organization_id=organization_id,
                priority=IncidentPriority.P1_CRITICAL,
                label="Critical",
                response_sla_minutes=5,
            )
        )
        found = await priorities_repo.get_for_priority(
            organization_id, IncidentPriority.P1_CRITICAL
        )
        assert found is not None
        assert found.response_sla_minutes == 5

    async def test_get_for_priority_is_none_without_an_override(
        self, priorities_repo: IncidentPriorityRepository, organization_id
    ) -> None:
        found = await priorities_repo.get_for_priority(organization_id, IncidentPriority.P2_HIGH)
        assert found is None

    async def test_list_for_org_lists_every_override(
        self, priorities_repo: IncidentPriorityRepository, organization_id
    ) -> None:
        await priorities_repo.create(
            IncidentPriorityRecord(
                organization_id=organization_id,
                priority=IncidentPriority.P1_CRITICAL,
                label="Critical",
            )
        )
        await priorities_repo.create(
            IncidentPriorityRecord(
                organization_id=organization_id, priority=IncidentPriority.P2_HIGH, label="High"
            )
        )
        listed = await priorities_repo.list_for_org(organization_id)
        assert len(listed) == 2


class TestIncidentStatusRepository:
    async def test_get_for_status_finds_a_display_record(
        self, statuses_repo: IncidentStatusRepository, organization_id
    ) -> None:
        await statuses_repo.create(
            IncidentStatusRecord(
                organization_id=organization_id,
                status=IncidentStatus.NEW,
                label="New",
                color="#ff0000",
            )
        )
        found = await statuses_repo.get_for_status(organization_id, IncidentStatus.NEW)
        assert found is not None
        assert found.color == "#ff0000"

    async def test_get_for_status_is_none_without_a_record(
        self, statuses_repo: IncidentStatusRepository, organization_id
    ) -> None:
        assert await statuses_repo.get_for_status(organization_id, IncidentStatus.RESOLVED) is None

    async def test_list_for_org_orders_by_display_order(
        self, statuses_repo: IncidentStatusRepository, organization_id
    ) -> None:
        await statuses_repo.create(
            IncidentStatusRecord(
                organization_id=organization_id,
                status=IncidentStatus.CLOSED,
                label="Closed",
                display_order=1,
            )
        )
        await statuses_repo.create(
            IncidentStatusRecord(
                organization_id=organization_id,
                status=IncidentStatus.NEW,
                label="New",
                display_order=0,
            )
        )
        listed = await statuses_repo.list_for_org(organization_id)
        assert [one.status for one in listed] == [
            str(IncidentStatus.NEW),
            str(IncidentStatus.CLOSED),
        ]
