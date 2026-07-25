"""Automatic audit trail for repository writes.

Per docs/018_Enterprise_Database_Framework.md.txt "AUDIT": automatic on
Insert/Update/Delete/Restore/Bulk Operations; stores Before/After/User/
Timestamp/Version. Every write goes through
:mod:`shared_core.database.repository`, so recording an audit entry there is
"automatic" from the caller's perspective -- no business code has to
remember to call this.

Entries are emitted as structured log events via
:meth:`shared_core.logging.logger.AIIOSLogger.audit` (Prompt 014) rather
than persisted to a database table -- this framework must not create
business tables (docs/018 "DO NOT IMPLEMENT"), and the audit log is exactly
the kind of write-once, query-by-log-pipeline data structured logging is
for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import inspect as sa_inspect

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.database.audit")


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One recorded change to an entity."""

    action: str
    entity_type: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    actor_id: str | None
    version: int | None
    timestamp: datetime


def snapshot(entity: Any) -> dict[str, Any]:
    """Return a plain ``{column: value}`` dict of every mapped column on *entity*."""
    mapper = sa_inspect(entity).mapper
    return {column.key: getattr(entity, column.key) for column in mapper.columns}


def capture_before(entity: Any) -> dict[str, Any]:
    """Capture pre-flush column values for *entity*'s pending changes.

    Uses SQLAlchemy's attribute history to recover the value each *changed*
    column had before the caller's in-memory mutation, and the current
    value for everything else -- giving :func:`record_audit` a genuine
    "before" snapshot even though the caller already mutated *entity* by
    the time ``repository.update()`` is called.
    """
    state = sa_inspect(entity)
    before: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        before[attr.key] = history.deleted[0] if history.deleted else getattr(entity, attr.key)
    return before


def record_audit(
    action: str,
    entity: Any,
    *,
    before: dict[str, Any] | None = None,
    actor_id: UUID | str | None = None,
) -> AuditEntry:
    """Record and emit an audit entry for a single-entity write.

    Args:
        action: One of ``shared_core.enums.AuditAction``'s values
            (``"create"``, ``"update"``, ``"delete"``, ``"restore"``, ...).
        entity: The entity as it stands *after* the write (for ``"delete"``,
            the entity as it stood immediately before removal).
        before: Column snapshot captured prior to the write, if applicable.
        actor_id: The user performing the write, if known.
    """
    after = None if action == "delete" else snapshot(entity)
    entity_id = getattr(entity, "id", None)
    entry = AuditEntry(
        action=action,
        entity_type=type(entity).__name__,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        actor_id=str(actor_id) if actor_id is not None else None,
        version=getattr(entity, "version", None),
        timestamp=datetime.now(UTC),
    )
    logger.audit(
        entry.action,
        actor_id=entry.actor_id,
        resource=entry.entity_type,
        entity_id=entry.entity_id,
        before=entry.before,
        after=entry.after,
        version=entry.version,
    )
    return entry


def record_bulk_audit(
    action: str,
    entity_type: str,
    *,
    count: int,
    actor_id: UUID | str | None = None,
) -> AuditEntry:
    """Record and emit an audit entry for a bulk write affecting *count* rows.

    Bulk operations don't carry individual before/after snapshots (that
    would mean loading every affected row just to audit it) -- the count
    itself, plus who triggered it and when, is what "Bulk Operations" audit
    coverage means at scale.
    """
    entry = AuditEntry(
        action=action,
        entity_type=entity_type,
        entity_id=None,
        before=None,
        after={"count": count},
        actor_id=str(actor_id) if actor_id is not None else None,
        version=None,
        timestamp=datetime.now(UTC),
    )
    logger.audit(
        entry.action,
        actor_id=entry.actor_id,
        resource=entry.entity_type,
        count=count,
    )
    return entry


__all__ = ["AuditEntry", "capture_before", "record_audit", "record_bulk_audit", "snapshot"]
