"""Deduplication registry maintenance ("DEDUPLICATION").

Owns the :class:`~app.models.alert_deduplication.AlertDeduplication`
fingerprint registry: recording a first occurrence, and consolidating
every repeat into it ("Event Consolidation").
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.alert_deduplication import AlertDeduplication
from app.models.enums import DeduplicationStrategy
from app.repositories.alert_deduplication import AlertDeduplicationRepository


class AlertDeduplicationService:
    """Maintains the fingerprint registry."""

    def __init__(self, entries: AlertDeduplicationRepository) -> None:
        self._entries = entries

    async def get_by_fingerprint(self, fingerprint: str) -> AlertDeduplication | None:
        """Return the registry entry for *fingerprint*, if any."""
        return await self._entries.get_by_fingerprint(fingerprint)

    async def register(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        fingerprint: str,
        primary_alert_id: UUID,
        strategy: DeduplicationStrategy = DeduplicationStrategy.FINGERPRINT,
        moment: datetime | None = None,
    ) -> AlertDeduplication:
        """Record a first occurrence for *fingerprint*."""
        now = moment or datetime.now(UTC)
        return await self._entries.create(
            AlertDeduplication(
                organization_id=organization_id,
                project_id=project_id,
                fingerprint=fingerprint,
                primary_alert_id=primary_alert_id,
                strategy=strategy,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        )

    async def record_occurrence(
        self, entry: AlertDeduplication, *, moment: datetime | None = None
    ) -> AlertDeduplication:
        """Consolidate one further occurrence into an existing entry."""
        entry.occurrence_count += 1
        entry.last_seen_at = moment or datetime.now(UTC)
        return await self._entries.update(entry)

    async def register_or_reassign(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        fingerprint: str,
        primary_alert_id: UUID,
        strategy: DeduplicationStrategy = DeduplicationStrategy.FINGERPRINT,
        moment: datetime | None = None,
    ) -> AlertDeduplication:
        """Register *fingerprint*, or re-point an existing entry at a new primary alert.

        ``fingerprint`` is unique in the schema, so a condition that
        recurs *outside* the deduplication window -- or after its
        earlier alert was resolved -- cannot register a second entry.
        Its existing entry is instead re-pointed at the newly raised
        alert and its own occurrence count continued, which also keeps
        the lifetime recurrence count of a flapping condition intact
        rather than resetting it every window.

        A real bug this service's own integration tests caught: the
        first implementation always inserted, and hit a genuine
        ``DuplicateRecordError`` the moment a condition recurred after
        its window elapsed.
        """
        now = moment or datetime.now(UTC)
        existing = await self._entries.get_by_fingerprint(fingerprint)
        if existing is None:
            return await self.register(
                organization_id=organization_id,
                project_id=project_id,
                fingerprint=fingerprint,
                primary_alert_id=primary_alert_id,
                strategy=strategy,
                moment=now,
            )
        existing.primary_alert_id = primary_alert_id
        existing.occurrence_count += 1
        existing.last_seen_at = now
        return await self._entries.update(existing)


__all__ = ["AlertDeduplicationService"]
