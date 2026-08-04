"""MaintenanceWindowService: creation, listing, and dispatch suppression.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from tests.conftest import RecordingPublisher, ago, soon, utcnow

from app.models.enums import JobPriority, MaintenanceWindowKind, MaintenanceWindowScope
from app.services.maintenance import MaintenanceWindowService

pytestmark = pytest.mark.asyncio


class TestCreateWindow:
    async def test_creates_a_window(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        created = await maintenance_service.create_window(
            organization_id, title="Patch Tuesday", starts_at=soon(1), ends_at=soon(2)
        )
        assert created.title == "Patch Tuesday"
        assert created.scope == MaintenanceWindowScope.ORGANIZATION
        assert created.kind == MaintenanceWindowKind.STANDARD

    async def test_ends_at_before_starts_at_raises(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await maintenance_service.create_window(
                organization_id, title="Bad window", starts_at=soon(2), ends_at=soon(1)
            )

    async def test_ends_at_equal_to_starts_at_raises(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        moment = soon(1)
        with pytest.raises(ValidationError):
            await maintenance_service.create_window(
                organization_id, title="Zero-length window", starts_at=moment, ends_at=moment
            )

    async def test_a_currently_active_window_publishes_maintenance_started(
        self,
        maintenance_service: MaintenanceWindowService,
        organization_id,
        publisher: RecordingPublisher,
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="Live now", starts_at=ago(1), ends_at=soon(1)
        )
        assert "MaintenanceStarted" in publisher.names

    async def test_a_future_window_does_not_publish_at_creation(
        self,
        maintenance_service: MaintenanceWindowService,
        organization_id,
        publisher: RecordingPublisher,
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="Future window", starts_at=soon(4), ends_at=soon(5)
        )
        assert "MaintenanceStarted" not in publisher.names

    async def test_a_past_window_does_not_publish_at_creation(
        self,
        maintenance_service: MaintenanceWindowService,
        organization_id,
        publisher: RecordingPublisher,
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="Already over", starts_at=ago(3), ends_at=ago(1)
        )
        assert "MaintenanceStarted" not in publisher.names

    async def test_accepts_a_blackout_window_with_override(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        created = await maintenance_service.create_window(
            organization_id,
            title="Emergency blackout",
            starts_at=soon(1),
            ends_at=soon(2),
            kind=MaintenanceWindowKind.BLACKOUT,
            allow_critical_override=True,
        )
        assert created.kind == MaintenanceWindowKind.BLACKOUT
        assert created.allow_critical_override is True


class TestGetAndList:
    async def test_get_raises_not_found_for_a_missing_window(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await maintenance_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        created = await maintenance_service.create_window(
            organization_id, title="Scoped window", starts_at=soon(1), ends_at=soon(2)
        )
        with pytest.raises(NotFoundError):
            await maintenance_service.get(uuid4(), created.id)

    async def test_list_windows_returns_every_window_for_the_org(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="A", starts_at=soon(1), ends_at=soon(2)
        )
        await maintenance_service.create_window(
            organization_id, title="B", starts_at=soon(3), ends_at=soon(4)
        )
        found = await maintenance_service.list_windows(organization_id)
        assert len(found) >= 2

    async def test_list_windows_excludes_other_organizations(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            uuid4(), title="Someone else's window", starts_at=soon(1), ends_at=soon(2)
        )
        found = await maintenance_service.list_windows(organization_id)
        assert found == []


class TestActiveWindows:
    async def test_a_currently_active_window_is_returned(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        created = await maintenance_service.create_window(
            organization_id, title="Live now", starts_at=ago(1), ends_at=soon(1)
        )
        active = await maintenance_service.active_windows(organization_id)
        assert created.id in {one.id for one in active}

    async def test_a_future_window_is_not_active(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="Future window", starts_at=soon(4), ends_at=soon(5)
        )
        active = await maintenance_service.active_windows(organization_id)
        assert active == []

    async def test_a_past_window_is_not_active(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="Already over", starts_at=ago(3), ends_at=ago(1)
        )
        active = await maintenance_service.active_windows(organization_id)
        assert active == []

    async def test_moment_defaults_to_now(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        created = await maintenance_service.create_window(
            organization_id, title="Live now", starts_at=ago(1), ends_at=soon(1)
        )
        active = await maintenance_service.active_windows(organization_id, moment=utcnow())
        assert created.id in {one.id for one in active}


class TestIsDispatchSuppressedFor:
    async def test_no_active_window_never_suppresses(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        suppressed = await maintenance_service.is_dispatch_suppressed_for(
            organization_id, priority=JobPriority.NORMAL
        )
        assert suppressed is False

    async def test_an_active_window_suppresses_a_normal_priority_job(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            organization_id, title="Live now", starts_at=ago(1), ends_at=soon(1)
        )
        suppressed = await maintenance_service.is_dispatch_suppressed_for(
            organization_id, priority=JobPriority.NORMAL
        )
        assert suppressed is True

    async def test_a_critical_job_dispatches_through_an_overriding_window(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            organization_id,
            title="Overridable",
            starts_at=ago(1),
            ends_at=soon(1),
            allow_critical_override=True,
        )
        suppressed = await maintenance_service.is_dispatch_suppressed_for(
            organization_id, priority=JobPriority.CRITICAL
        )
        assert suppressed is False

    async def test_a_critical_job_is_still_suppressed_by_a_non_overriding_window(
        self, maintenance_service: MaintenanceWindowService, organization_id
    ) -> None:
        await maintenance_service.create_window(
            organization_id,
            title="Non-overridable",
            starts_at=ago(1),
            ends_at=soon(1),
            allow_critical_override=False,
        )
        suppressed = await maintenance_service.is_dispatch_suppressed_for(
            organization_id, priority=JobPriority.CRITICAL
        )
        assert suppressed is True
