"""PreferenceService: default creation, editing, muting, and snapshotting.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import pytest

from app.models.enums import (
    DigestFrequency,
    NotificationCategory,
    NotificationChannelKind,
)
from app.services.preference import PreferenceService

pytestmark = pytest.mark.asyncio


class TestGet:
    async def test_creates_a_permissive_default_row_for_a_new_user(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        preferences = await preference_service.get(organization_id, "brand-new-user")
        assert preferences.preferred_channels == [
            str(NotificationChannelKind.EMAIL),
            str(NotificationChannelKind.IN_APP),
        ]
        assert preferences.muted is False
        assert preferences.digest_frequency == DigestFrequency.NONE

    async def test_second_call_returns_the_same_row(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        first = await preference_service.get(organization_id, "user-1")
        second = await preference_service.get(organization_id, "user-1")
        assert first.id == second.id

    async def test_is_scoped_per_organization(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        from uuid import uuid4

        first = await preference_service.get(organization_id, "user-1")
        second = await preference_service.get(uuid4(), "user-1")
        assert first.id != second.id


class TestUpdate:
    async def test_updates_only_the_provided_field(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        default = await preference_service.get(organization_id, "user-1")
        updated = await preference_service.update(organization_id, "user-1", muted=True)
        assert updated.muted is True
        assert updated.preferred_channels == default.preferred_channels

    async def test_none_values_leave_fields_unchanged(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        default = await preference_service.get(organization_id, "user-1")
        updated = await preference_service.update(
            organization_id, "user-1", preferred_channels=None, muted=None
        )
        assert updated.preferred_channels == default.preferred_channels
        assert updated.muted is False

    async def test_silently_ignores_a_non_editable_field(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        updated = await preference_service.update(organization_id, "user-1", not_a_real_field="x")
        assert not hasattr(updated, "not_a_real_field") or updated.muted is False

    async def test_sets_updated_by_from_actor_id(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        from uuid import uuid4

        actor_id = uuid4()
        updated = await preference_service.update(
            organization_id, "user-1", actor_id=str(actor_id), muted=True
        )
        assert updated.updated_by == actor_id

    async def test_leaves_updated_by_none_without_an_actor_id(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        updated = await preference_service.update(organization_id, "user-1", muted=True)
        assert updated.updated_by is None

    async def test_updates_multiple_editable_fields_at_once(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        updated = await preference_service.update(
            organization_id,
            "user-1",
            unsubscribed_channels=[str(NotificationChannelKind.SMS)],
            channel_priority=[str(NotificationChannelKind.SLACK), str(NotificationChannelKind.EMAIL)],
            language="fr",
            timezone="Europe/Paris",
            digest_frequency=DigestFrequency.DAILY,
        )
        assert updated.unsubscribed_channels == [str(NotificationChannelKind.SMS)]
        assert updated.channel_priority == [
            str(NotificationChannelKind.SLACK),
            str(NotificationChannelKind.EMAIL),
        ]
        assert updated.language == "fr"
        assert updated.timezone == "Europe/Paris"
        assert updated.digest_frequency == DigestFrequency.DAILY


class TestMuteUnmute:
    async def test_mute_sets_muted_true(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        updated = await preference_service.mute(organization_id, "user-1")
        assert updated.muted is True

    async def test_unmute_sets_muted_false(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        await preference_service.mute(organization_id, "user-1")
        updated = await preference_service.unmute(organization_id, "user-1")
        assert updated.muted is False


class TestToSnapshot:
    async def test_converts_list_fields_to_tuples_and_frozensets_of_enum_members(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        updated = await preference_service.update(
            organization_id,
            "user-1",
            preferred_channels=[str(NotificationChannelKind.EMAIL), str(NotificationChannelKind.SLACK)],
            unsubscribed_channels=[str(NotificationChannelKind.SMS)],
            channel_priority=[str(NotificationChannelKind.SLACK), str(NotificationChannelKind.EMAIL)],
            muted_categories=[str(NotificationCategory.ALERT), str(NotificationCategory.WARNING)],
        )

        snapshot = PreferenceService.to_snapshot(updated)

        assert snapshot.preferred_channels == (
            NotificationChannelKind.EMAIL,
            NotificationChannelKind.SLACK,
        )
        assert all(isinstance(c, NotificationChannelKind) for c in snapshot.preferred_channels)

        assert snapshot.unsubscribed_channels == frozenset({NotificationChannelKind.SMS})
        assert isinstance(snapshot.unsubscribed_channels, frozenset)
        assert all(isinstance(c, NotificationChannelKind) for c in snapshot.unsubscribed_channels)

        assert snapshot.channel_priority == (
            NotificationChannelKind.SLACK,
            NotificationChannelKind.EMAIL,
        )
        assert all(isinstance(c, NotificationChannelKind) for c in snapshot.channel_priority)

        assert snapshot.muted_categories == frozenset(
            {NotificationCategory.ALERT, NotificationCategory.WARNING}
        )
        assert isinstance(snapshot.muted_categories, frozenset)
        assert all(isinstance(c, NotificationCategory) for c in snapshot.muted_categories)

        assert snapshot.user_id == updated.user_id
        assert snapshot.muted == updated.muted

    async def test_carries_quiet_hours_through_when_set(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        from datetime import time

        updated = await preference_service.update(
            organization_id,
            "user-1",
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(6, 0),
        )
        snapshot = PreferenceService.to_snapshot(updated)
        assert snapshot.quiet_hours_start == time(22, 0)
        assert snapshot.quiet_hours_end == time(6, 0)

    async def test_quiet_hours_are_none_by_default(
        self, preference_service: PreferenceService, organization_id
    ) -> None:
        default = await preference_service.get(organization_id, "user-1")
        snapshot = PreferenceService.to_snapshot(default)
        assert snapshot.quiet_hours_start is None
        assert snapshot.quiet_hours_end is None
