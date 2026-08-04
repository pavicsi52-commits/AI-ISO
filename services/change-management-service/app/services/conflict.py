"""Detecting scheduling conflicts between changes.

Wraps ``app/conflicts/engine.py`` with the database: pulls every other
scheduled change, compares windows and footprints pairwise, and records
whatever the pure engine finds as durable ``ChangeConflict`` rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.conflicts.engine import ChangeWindow, detect_conflicts
from app.models.change import ChangeRequest
from app.models.conflict import ChangeConflict
from app.models.enums import ConflictStatus, conflict_kind_of
from app.repositories.change import ChangeRequestRepository
from app.repositories.conflict import ChangeConflictRepository

logger = get_logger("app.services.conflict")


def _window_for(change: ChangeRequest) -> ChangeWindow | None:
    """The window a change occupies, or ``None`` if it is not scheduled yet.

    An unscheduled change has nothing to conflict over -- its
    ``scheduled_start_at``/``scheduled_end_at`` are what conflict
    detection actually compares.
    """
    if change.scheduled_start_at is None or change.scheduled_end_at is None:
        return None
    return ChangeWindow(
        starts_at=change.scheduled_start_at,
        ends_at=change.scheduled_end_at,
        assets=frozenset(change.affected_assets),
        services=frozenset(change.affected_services),
        applications=frozenset(change.affected_applications),
    )


class ConflictService:
    """Scheduling conflict detection and resolution."""

    def __init__(
        self,
        conflicts: ChangeConflictRepository,
        changes: ChangeRequestRepository,
        *,
        slack_hours: int = 4,
    ) -> None:
        self._conflicts = conflicts
        self._changes = changes
        self._slack = timedelta(hours=slack_hours)

    async def detect_for_change(
        self, organization_id: UUID, change_id: UUID, *, now: datetime | None = None
    ) -> list[ChangeConflict]:
        """Compare one change against every other scheduled change, recording new conflicts.

        Idempotent: a pair already recorded for a given kind is not
        duplicated -- the repository's own uniqueness constraint on
        ``(change_id, conflicting_change_id, kind)`` is the backstop,
        but this checks first so a re-run does not raise trying to
        insert a row that already exists.
        """
        moment = now or datetime.now(UTC)
        target = await self._changes.require_in_org(organization_id, change_id)
        window = _window_for(target)
        if window is None:
            return []

        existing = await self._conflicts.list_for_change(organization_id, change_id)
        existing_pairs = {
            (one.change_id, one.conflicting_change_id, conflict_kind_of(one.kind))
            for one in existing
        }

        others = await self._changes.list_scheduled_between(
            organization_id, start=window.starts_at - self._slack, end=window.ends_at + self._slack
        )
        created: list[ChangeConflict] = []
        for other in others:
            if other.id == change_id:
                continue
            other_window = _window_for(other)
            if other_window is None:
                continue
            for kind in detect_conflicts(window, other_window, slack=self._slack):
                if (change_id, other.id, kind) in existing_pairs:
                    continue
                row = await self._conflicts.create(
                    ChangeConflict(
                        organization_id=organization_id,
                        change_id=change_id,
                        conflicting_change_id=other.id,
                        kind=kind,
                        status=ConflictStatus.DETECTED,
                        detail=(
                            f"{target.reference} and {other.reference} both scheduled "
                            f"{window.starts_at.isoformat()}-{window.ends_at.isoformat()} "
                            f"({kind!s})."
                        ),
                        detected_at=moment,
                    )
                )
                created.append(row)
                existing_pairs.add((change_id, other.id, kind))
        return created

    async def acknowledge(self, organization_id: UUID, conflict_id: UUID) -> ChangeConflict:
        """Acknowledge a detected conflict.

        Raises:
            NotFoundError: If it does not exist here.
        """
        row = await self._conflicts.require_in_org(organization_id, conflict_id)
        row.status = ConflictStatus.ACKNOWLEDGED
        return await self._conflicts.update(row)

    async def resolve(
        self, organization_id: UUID, conflict_id: UUID, *, resolved_by: str, note: str | None = None
    ) -> ChangeConflict:
        """Resolve a conflict -- one of the changes was rescheduled, or the collision was accepted.

        Raises:
            NotFoundError: If it does not exist here.
        """
        row = await self._conflicts.require_in_org(organization_id, conflict_id)
        row.status = ConflictStatus.RESOLVED
        row.resolved_by = resolved_by
        row.resolved_at = datetime.now(UTC)
        row.resolution_note = note
        return await self._conflicts.update(row)

    async def list_for_change(self, organization_id: UUID, change_id: UUID) -> list[ChangeConflict]:
        """Every conflict naming this change on either side."""
        return await self._conflicts.list_for_change(organization_id, change_id)

    async def list_active(self, organization_id: UUID) -> list[ChangeConflict]:
        """Every conflict still open across the organization."""
        return await self._conflicts.list_active(organization_id)


__all__ = ["ConflictService"]
