"""User notification preferences.

The persisted, per-organization equivalent of `shared_core.notifications
.preferences.PreferencesStore`: :meth:`PreferenceService.get` creates a
permissive default row the first time a user is seen, mirroring
`PreferencesStore.get`'s own "create a permissive default if none exist
yet" behaviour.
"""

from __future__ import annotations

from datetime import time
from typing import Any
from uuid import UUID

from app.models.enums import (
    DigestFrequency,
    NotificationChannelKind,
    notification_category_of,
    notification_channel_kind_of,
)
from app.models.preference import NotificationPreference
from app.repositories.preference import NotificationPreferenceRepository
from app.routing.engine import PreferenceSnapshot

_DEFAULT_PREFERRED_CHANNELS = (NotificationChannelKind.EMAIL, NotificationChannelKind.IN_APP)

_EDITABLE_FIELDS = frozenset(
    {
        "preferred_channels",
        "muted_categories",
        "unsubscribed_channels",
        "channel_priority",
        "device_tokens",
        "quiet_hours_start",
        "quiet_hours_end",
        "language",
        "timezone",
        "digest_frequency",
        "muted",
        "priority_overrides",
    }
)


class PreferenceService:
    """One user's own notification preferences within one organization."""

    def __init__(self, preferences: NotificationPreferenceRepository) -> None:
        self._preferences = preferences

    async def get(self, organization_id: UUID, user_id: str) -> NotificationPreference:
        """*user_id*'s preferences, creating a permissive default row if none exist yet."""
        stored = await self._preferences.get_for_user(organization_id, user_id)
        if stored is not None:
            return stored
        return await self._preferences.create(
            NotificationPreference(
                organization_id=organization_id,
                user_id=user_id,
                preferred_channels=[str(channel) for channel in _DEFAULT_PREFERRED_CHANNELS],
                digest_frequency=DigestFrequency.NONE,
            )
        )

    async def update(
        self, organization_id: UUID, user_id: str, *, actor_id: str | None = None, **fields: Any
    ) -> NotificationPreference:
        """Edit a user's editable preference fields.

        Silently ignores any key in *fields* outside the editable set.
        """
        stored = await self.get(organization_id, user_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._preferences.update(stored)

    async def mute(self, organization_id: UUID, user_id: str) -> NotificationPreference:
        """Mute every notification for this user ("Do Not Disturb")."""
        stored = await self.get(organization_id, user_id)
        stored.muted = True
        return await self._preferences.update(stored)

    async def unmute(self, organization_id: UUID, user_id: str) -> NotificationPreference:
        """Unmute this user."""
        stored = await self.get(organization_id, user_id)
        stored.muted = False
        return await self._preferences.update(stored)

    @staticmethod
    def to_snapshot(preferences: NotificationPreference) -> PreferenceSnapshot:
        """Convert a stored preference row into the snapshot :mod:`app.routing.engine` reads."""
        quiet_start = preferences.quiet_hours_start
        quiet_end = preferences.quiet_hours_end
        return PreferenceSnapshot(
            user_id=preferences.user_id,
            preferred_channels=tuple(
                notification_channel_kind_of(value) for value in preferences.preferred_channels
            ),
            muted_categories=frozenset(
                notification_category_of(value) for value in preferences.muted_categories
            ),
            unsubscribed_channels=frozenset(
                notification_channel_kind_of(value) for value in preferences.unsubscribed_channels
            ),
            channel_priority=tuple(
                notification_channel_kind_of(value) for value in preferences.channel_priority
            ),
            muted=preferences.muted,
            quiet_hours_start=quiet_start if isinstance(quiet_start, time) else None,
            quiet_hours_end=quiet_end if isinstance(quiet_end, time) else None,
        )


__all__ = ["PreferenceService"]
