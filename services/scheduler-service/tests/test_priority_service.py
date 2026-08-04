"""PriorityService: an organization's own priority-escalation policy.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.enums import JobPriority
from app.services.priority import PriorityService

pytestmark = pytest.mark.asyncio


class TestSetPolicy:
    async def test_set_policy_creates_a_new_policy_when_none_exists(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        created = await priority_service.set_policy(
            organization_id,
            JobPriority.HIGH,
            label="Escalate fast",
            color="red",
            escalate_after_minutes=15,
            escalate_to=JobPriority.CRITICAL,
        )
        assert created.priority == JobPriority.HIGH
        assert created.label == "Escalate fast"
        assert created.color == "red"
        assert created.escalate_after_minutes == 15
        assert created.escalate_to == JobPriority.CRITICAL

    async def test_set_policy_allows_optional_fields_to_be_omitted(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        created = await priority_service.set_policy(
            organization_id, JobPriority.BACKGROUND, label="Background work"
        )
        assert created.color is None
        assert created.escalate_after_minutes is None
        assert created.escalate_to is None

    async def test_set_policy_updates_the_existing_row_instead_of_creating_a_duplicate(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        first = await priority_service.set_policy(
            organization_id, JobPriority.LOW, label="Initial label"
        )
        second = await priority_service.set_policy(
            organization_id,
            JobPriority.LOW,
            label="Updated label",
            color="blue",
            escalate_after_minutes=30,
            escalate_to=JobPriority.NORMAL,
        )

        assert second.id == first.id
        assert second.label == "Updated label"
        assert second.color == "blue"
        assert second.escalate_after_minutes == 30
        assert second.escalate_to == JobPriority.NORMAL

        every_band = await priority_service.list_policies(organization_id)
        assert len(every_band) == 1


class TestGetPolicy:
    async def test_get_policy_returns_none_when_unconfigured(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        found = await priority_service.get_policy(organization_id, JobPriority.CRITICAL)
        assert found is None

    async def test_get_policy_returns_the_configured_policy(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        await priority_service.set_policy(organization_id, JobPriority.NORMAL, label="Standard")
        found = await priority_service.get_policy(organization_id, JobPriority.NORMAL)
        assert found is not None
        assert found.label == "Standard"


class TestListPolicies:
    async def test_list_policies_returns_empty_list_when_nothing_configured(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        found = await priority_service.list_policies(organization_id)
        assert found == []

    async def test_list_policies_returns_every_band_this_organization_configured(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        await priority_service.set_policy(organization_id, JobPriority.CRITICAL, label="Urgent")
        await priority_service.set_policy(organization_id, JobPriority.HIGH, label="Important")
        await priority_service.set_policy(organization_id, JobPriority.LOW, label="Whenever")

        found = await priority_service.list_policies(organization_id)
        assert len(found) == 3
        assert {policy.priority for policy in found} == {
            JobPriority.CRITICAL,
            JobPriority.HIGH,
            JobPriority.LOW,
        }

    async def test_list_policies_is_scoped_to_its_own_organization(
        self, priority_service: PriorityService, organization_id
    ) -> None:
        other_organization_id = uuid4()
        await priority_service.set_policy(organization_id, JobPriority.HIGH, label="Mine")
        await priority_service.set_policy(other_organization_id, JobPriority.HIGH, label="Theirs")

        found = await priority_service.list_policies(organization_id)
        assert len(found) == 1
        assert found[0].label == "Mine"
