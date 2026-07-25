"""Event audit trail.

Per docs/020_Enterprise_Event_Framework.md.txt "AUDIT LOGGING": "Every
event published/consumed... audited." Emitted as structured log events
via :meth:`shared_core.logging.logger.AIIOSLogger.audit` (Prompt 014)
rather than persisted to a database table -- same reasoning as
:mod:`shared_core.database.audit`: this framework must not create
business tables (docs/020 "DO NOT IMPLEMENT"), and an append-only audit
trail is exactly what structured logging already covers. Payloads are
masked via :func:`shared_core.events.validator.mask_sensitive_payload`
before they ever reach the log line.
"""

from __future__ import annotations

from shared_core.events.base import BaseEvent
from shared_core.events.validator import mask_sensitive_payload
from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.events.audit")


def audit_publish(event: BaseEvent) -> None:
    """Record that *event* was published."""
    masked = mask_sensitive_payload(event)
    logger.audit(
        "event.publish",
        actor_id=str(masked.user_id) if masked.user_id else None,
        resource=masked.event_name,
        event_id=str(masked.event_id),
        event_version=masked.event_version,
        event_type=masked.event_type.value,
        organization_id=str(masked.organization_id) if masked.organization_id else None,
        correlation_id=masked.correlation_id,
        payload=masked.payload,
    )


def audit_consume(event: BaseEvent, *, outcome: str = "success") -> None:
    """Record that *event* was consumed by a subscriber handler."""
    masked = mask_sensitive_payload(event)
    logger.audit(
        "event.consume",
        actor_id=str(masked.user_id) if masked.user_id else None,
        resource=masked.event_name,
        outcome=outcome,
        event_id=str(masked.event_id),
        event_version=masked.event_version,
        correlation_id=masked.correlation_id,
    )


def audit_replay(event_name: str, *, count: int, actor_id: str | None = None) -> None:
    """Record that *count* events matching *event_name* (or ``"*"`` for all) were replayed."""
    logger.audit(
        "event.replay",
        actor_id=actor_id,
        resource=event_name,
        count=count,
    )


def audit_failure(event: BaseEvent, *, error: str) -> None:
    """Record that processing *event* failed."""
    masked = mask_sensitive_payload(event)
    logger.audit(
        "event.failure",
        actor_id=str(masked.user_id) if masked.user_id else None,
        resource=masked.event_name,
        outcome="failure",
        event_id=str(masked.event_id),
        correlation_id=masked.correlation_id,
        error=error,
    )


__all__ = ["audit_consume", "audit_failure", "audit_publish", "audit_replay"]
