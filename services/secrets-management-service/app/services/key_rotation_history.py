"""Encryption-key rotation history ("KEY MANAGEMENT": Key Rotation, Key
Versioning, Key Revocation). Distinct from
:class:`~app.services.rotation_history.SecretRotationHistoryService`,
which tracks rotation of secrets' own values. Used internally by
:class:`~app.services.encryption_key.EncryptionKeyService`; has no REST
surface of its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.key_rotation_history import KeyRotationHistoryEntry
from app.repositories.key_rotation_history import KeyRotationHistoryRepository


class KeyRotationHistoryService:
    """Records and lists encryption-key rotation events."""

    def __init__(self, history: KeyRotationHistoryRepository) -> None:
        self._history = history

    async def record(
        self,
        *,
        organization_id: UUID,
        encryption_key_id: UUID,
        previous_key_id: UUID | None,
        rotated_by: UUID | None,
        reason: str | None,
        secrets_migrated_count: int,
    ) -> KeyRotationHistoryEntry:
        """Record one encryption-key rotation event."""
        return await self._history.create(
            KeyRotationHistoryEntry(
                organization_id=organization_id,
                encryption_key_id=encryption_key_id,
                previous_key_id=previous_key_id,
                rotated_by=rotated_by,
                reason=reason,
                secrets_migrated_count=secrets_migrated_count,
                rotated_at=datetime.now(UTC),
            )
        )

    async def list_all(self) -> list[KeyRotationHistoryEntry]:
        """Every encryption-key rotation event ever recorded, newest first."""
        return await self._history.list_all()


__all__ = ["KeyRotationHistoryService"]
