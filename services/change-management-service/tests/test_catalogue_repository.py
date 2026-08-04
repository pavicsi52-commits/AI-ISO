"""Catalogue repositories: organization-configurable category/type/priority/status records.

Not yet wired to any route (see `app/api/deps.py`'s own note on
`CategoryRepo`/`TypeRepo`/`PriorityRepo`/`StatusRepo` being kept as
available infrastructure), but real, shipped code against real
PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.catalogue import (
    ChangeCategoryRecord,
    ChangePriorityRecord,
    ChangeStatusRecord,
    ChangeTypeRecord,
)
from app.models.enums import ChangePriority, ChangeStatus, ChangeType
from app.repositories.catalogue import (
    ChangeCategoryRepository,
    ChangePriorityRepository,
    ChangeStatusRepository,
    ChangeTypeRepository,
)

pytestmark = pytest.mark.asyncio


class TestChangeCategoryRepository:
    async def test_get_by_slug_finds_a_created_record(
        self, categories_repo: ChangeCategoryRepository, organization_id: uuid.UUID
    ) -> None:
        created = await categories_repo.create(
            ChangeCategoryRecord(
                organization_id=organization_id, slug="db-changes", name="Database Changes"
            )
        )
        found = await categories_repo.get_by_slug(organization_id, "db-changes")
        assert found is not None
        assert found.id == created.id

    async def test_get_by_slug_returns_none_when_missing(
        self, categories_repo: ChangeCategoryRepository, organization_id: uuid.UUID
    ) -> None:
        assert await categories_repo.get_by_slug(organization_id, "no-such-slug") is None

    async def test_get_by_slug_is_scoped_to_its_organization(
        self, categories_repo: ChangeCategoryRepository, organization_id: uuid.UUID
    ) -> None:
        await categories_repo.create(
            ChangeCategoryRecord(organization_id=organization_id, slug="db-changes", name="DB")
        )
        assert await categories_repo.get_by_slug(uuid.uuid4(), "db-changes") is None

    async def test_list_for_org_orders_by_display_order_then_name(
        self, categories_repo: ChangeCategoryRepository, organization_id: uuid.UUID
    ) -> None:
        await categories_repo.create(
            ChangeCategoryRecord(
                organization_id=organization_id,
                slug="second",
                name="Second",
                display_order=2,
            )
        )
        await categories_repo.create(
            ChangeCategoryRecord(
                organization_id=organization_id, slug="first", name="First", display_order=1
            )
        )
        found = await categories_repo.list_for_org(organization_id)
        assert [one.slug for one in found] == ["first", "second"]

    async def test_list_for_org_excludes_other_organizations(
        self, categories_repo: ChangeCategoryRepository, organization_id: uuid.UUID
    ) -> None:
        await categories_repo.create(
            ChangeCategoryRecord(organization_id=uuid.uuid4(), slug="other-org", name="Other")
        )
        found = await categories_repo.list_for_org(organization_id)
        assert found == []


class TestChangeTypeRepository:
    async def test_get_for_type_finds_a_created_override(
        self, types_repo: ChangeTypeRepository, organization_id: uuid.UUID
    ) -> None:
        created = await types_repo.create(
            ChangeTypeRecord(
                organization_id=organization_id,
                change_type=ChangeType.STANDARD,
                label="Standard",
                requires_cab=True,
            )
        )
        found = await types_repo.get_for_type(organization_id, ChangeType.STANDARD)
        assert found is not None
        assert found.id == created.id
        assert found.requires_cab is True

    async def test_get_for_type_returns_none_when_no_override_exists(
        self, types_repo: ChangeTypeRepository, organization_id: uuid.UUID
    ) -> None:
        assert await types_repo.get_for_type(organization_id, ChangeType.EMERGENCY) is None

    async def test_list_for_org_orders_by_display_order(
        self, types_repo: ChangeTypeRepository, organization_id: uuid.UUID
    ) -> None:
        await types_repo.create(
            ChangeTypeRecord(
                organization_id=organization_id,
                change_type=ChangeType.NORMAL,
                label="Normal",
                display_order=1,
            )
        )
        await types_repo.create(
            ChangeTypeRecord(
                organization_id=organization_id,
                change_type=ChangeType.STANDARD,
                label="Standard",
                display_order=0,
            )
        )
        found = await types_repo.list_for_org(organization_id)
        assert [one.change_type for one in found] == ["standard", "normal"]


class TestChangePriorityRepository:
    async def test_get_for_priority_finds_a_created_override(
        self, priorities_repo: ChangePriorityRepository, organization_id: uuid.UUID
    ) -> None:
        created = await priorities_repo.create(
            ChangePriorityRecord(
                organization_id=organization_id,
                priority=ChangePriority.CRITICAL,
                label="Critical",
                approval_window_hours=1,
                color="#ff0000",
            )
        )
        found = await priorities_repo.get_for_priority(organization_id, ChangePriority.CRITICAL)
        assert found is not None
        assert found.id == created.id
        assert found.approval_window_hours == 1

    async def test_get_for_priority_returns_none_when_no_override_exists(
        self, priorities_repo: ChangePriorityRepository, organization_id: uuid.UUID
    ) -> None:
        assert await priorities_repo.get_for_priority(organization_id, ChangePriority.LOW) is None

    async def test_list_for_org_excludes_other_organizations(
        self, priorities_repo: ChangePriorityRepository, organization_id: uuid.UUID
    ) -> None:
        await priorities_repo.create(
            ChangePriorityRecord(
                organization_id=uuid.uuid4(), priority=ChangePriority.HIGH, label="High"
            )
        )
        found = await priorities_repo.list_for_org(organization_id)
        assert found == []


class TestChangeStatusRepository:
    async def test_get_for_status_finds_a_created_record(
        self, statuses_repo: ChangeStatusRepository, organization_id: uuid.UUID
    ) -> None:
        created = await statuses_repo.create(
            ChangeStatusRecord(
                organization_id=organization_id,
                status=ChangeStatus.CAB_REVIEW,
                label="Board Review",
                color="#0000ff",
            )
        )
        found = await statuses_repo.get_for_status(organization_id, ChangeStatus.CAB_REVIEW)
        assert found is not None
        assert found.id == created.id
        assert found.label == "Board Review"

    async def test_get_for_status_returns_none_when_no_record_exists(
        self, statuses_repo: ChangeStatusRepository, organization_id: uuid.UUID
    ) -> None:
        assert await statuses_repo.get_for_status(organization_id, ChangeStatus.DRAFT) is None

    async def test_list_for_org_orders_by_display_order(
        self, statuses_repo: ChangeStatusRepository, organization_id: uuid.UUID
    ) -> None:
        await statuses_repo.create(
            ChangeStatusRecord(
                organization_id=organization_id,
                status=ChangeStatus.CLOSED,
                label="Closed",
                display_order=1,
            )
        )
        await statuses_repo.create(
            ChangeStatusRecord(
                organization_id=organization_id,
                status=ChangeStatus.DRAFT,
                label="Draft",
                display_order=0,
            )
        )
        found = await statuses_repo.list_for_org(organization_id)
        assert [one.status for one in found] == ["draft", "closed"]
