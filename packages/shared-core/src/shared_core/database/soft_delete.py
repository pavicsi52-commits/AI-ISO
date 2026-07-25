"""Soft delete.

Per docs/018_Enterprise_Database_Framework.md.txt "SOFT DELETE": delete sets
``deleted_at``/``deleted_by``/``is_active=false`` rather than removing the
row; supports Restore, Purge, and Audit. :mod:`shared_core.database.repository`
is the only caller most services need -- these are the underlying,
independently-testable mutations it (and any decorator-driven path such as
``@soft_delete``) applies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class SoftDeletable(Protocol):
    """Structural type for any entity carrying the soft-delete/audit columns."""

    deleted_at: datetime | None
    deleted_by: UUID | None
    is_active: bool


def mark_deleted(entity: SoftDeletable, *, deleted_by: UUID | None = None) -> None:
    """Set *entity*'s soft-delete columns. Idempotent."""
    entity.deleted_at = datetime.now(UTC)
    entity.deleted_by = deleted_by
    entity.is_active = False


def mark_restored(entity: SoftDeletable) -> None:
    """Clear *entity*'s soft-delete columns, reactivating it. Idempotent."""
    entity.deleted_at = None
    entity.deleted_by = None
    entity.is_active = True


async def purge(session: AsyncSession, entity: Any) -> None:
    """Permanently remove *entity* from the database.

    Distinct from soft delete: this issues a real ``DELETE``. Reserved for
    retention-policy cleanup of already soft-deleted records, never for a
    normal user-facing delete action.
    """
    await session.delete(entity)
    await session.flush()


__all__ = ["SoftDeletable", "mark_deleted", "mark_restored", "purge"]
