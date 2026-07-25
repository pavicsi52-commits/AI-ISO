"""Secret rotation history.

Per docs/035 "SECRET ROTATION": Rotation History, Failure Recovery.
Records the outcome of every rotation attempt against a secret's own
value -- distinct from
:class:`~app.services.key_rotation_history.KeyRotationHistoryService`,
which tracks rotation of the *encryption keys* protecting secrets.
Used internally by :class:`~app.services.secret.SecretService.rotate`;
has no REST surface of its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import RotationOutcome, RotationTrigger
from app.models.secret_rotation import SecretRotationEntry
from app.repositories.secret_rotation import SecretRotationRepository


class SecretRotationHistoryService:
    """Records and lists rotation attempts for a secret."""

    def __init__(self, rotations: SecretRotationRepository) -> None:
        self._rotations = rotations

    async def record(
        self,
        secret_id: UUID,
        *,
        organization_id: UUID,
        rotated_by: UUID | None,
        trigger: RotationTrigger,
        previous_version_number: int,
        new_version_number: int | None,
        outcome: RotationOutcome,
        error_message: str | None = None,
    ) -> SecretRotationEntry:
        """Record one rotation attempt."""
        return await self._rotations.create(
            SecretRotationEntry(
                secret_id=secret_id,
                organization_id=organization_id,
                rotated_by=rotated_by,
                trigger=trigger,
                previous_version_number=previous_version_number,
                new_version_number=new_version_number,
                outcome=outcome,
                error_message=error_message,
                rotated_at=datetime.now(UTC),
            )
        )

    async def list_for_secret(self, secret_id: UUID) -> list[SecretRotationEntry]:
        """Every rotation attempt for *secret_id*, newest first."""
        return await self._rotations.list_for_secret(secret_id)


__all__ = ["SecretRotationHistoryService"]
