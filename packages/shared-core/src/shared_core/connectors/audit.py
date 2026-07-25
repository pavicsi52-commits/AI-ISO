"""Connector audit trail.

Per docs/027_Enterprise_Connector_SDK.md.txt "AUDIT": Connection,
Authentication, Commands, Transfers, Inventory, Discovery, Failures,
Disconnect. Emitted as structured log events via
:meth:`shared_core.logging.logger.AIIOSLogger.audit` (Prompt 014)
rather than persisted to a database table -- same reasoning as every
other Prompt 018-026 framework's own audit.py.
"""

from __future__ import annotations

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.connectors.audit")


def audit_connect(provider: str, target: str, *, actor_id: str | None = None) -> None:
    """Record a connection attempt ("Connection")."""
    logger.audit("connector.connect", actor_id=actor_id, resource=target, provider=provider)


def audit_authenticate(
    provider: str, target: str, *, outcome: str, actor_id: str | None = None
) -> None:
    """Record an authentication attempt ("Authentication")."""
    logger.audit(
        "connector.authenticate",
        actor_id=actor_id,
        resource=target,
        outcome=outcome,
        provider=provider,
    )


def audit_command(
    provider: str, target: str, *, command: str, outcome: str, actor_id: str | None = None
) -> None:
    """Record a command execution ("Commands")."""
    logger.audit(
        "connector.command",
        actor_id=actor_id,
        resource=target,
        outcome=outcome,
        provider=provider,
        command=command,
    )


def audit_transfer(
    provider: str,
    target: str,
    *,
    direction: str,
    path: str,
    outcome: str,
    actor_id: str | None = None,
) -> None:
    """Record a file transfer ("Transfers")."""
    logger.audit(
        "connector.transfer",
        actor_id=actor_id,
        resource=target,
        outcome=outcome,
        provider=provider,
        direction=direction,
        path=path,
    )


def audit_inventory(
    provider: str, target: str, *, outcome: str, actor_id: str | None = None
) -> None:
    """Record an inventory collection ("Inventory")."""
    logger.audit(
        "connector.inventory",
        actor_id=actor_id,
        resource=target,
        outcome=outcome,
        provider=provider,
    )


def audit_discovery(
    provider: str, target: str, *, outcome: str, actor_id: str | None = None
) -> None:
    """Record a discovery run ("Discovery")."""
    logger.audit(
        "connector.discovery",
        actor_id=actor_id,
        resource=target,
        outcome=outcome,
        provider=provider,
    )


def audit_failure(
    provider: str, target: str, *, operation: str, error: str, actor_id: str | None = None
) -> None:
    """Record any operation's failure ("Failures")."""
    logger.audit(
        "connector.failure",
        actor_id=actor_id,
        resource=target,
        outcome="failure",
        provider=provider,
        operation=operation,
        error=error,
    )


def audit_disconnect(provider: str, target: str, *, actor_id: str | None = None) -> None:
    """Record a disconnect ("Disconnect")."""
    logger.audit("connector.disconnect", actor_id=actor_id, resource=target, provider=provider)


__all__ = [
    "audit_authenticate",
    "audit_command",
    "audit_connect",
    "audit_disconnect",
    "audit_discovery",
    "audit_failure",
    "audit_inventory",
    "audit_transfer",
]
