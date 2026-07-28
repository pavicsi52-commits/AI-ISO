"""Acknowledgement records ("ACKNOWLEDGEMENT")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.alert_acknowledgement import AlertAcknowledgement
from app.models.enums import AcknowledgementType
from app.repositories.alert_acknowledgement import AlertAcknowledgementRepository


class AlertAcknowledgementService:
    """Records and reads alert acknowledgements."""

    def __init__(self, acknowledgements: AlertAcknowledgementRepository) -> None:
        self._acknowledgements = acknowledgements

    async def list_for_alert(self, alert_id: UUID) -> list[AlertAcknowledgement]:
        """Every acknowledgement recorded for *alert_id*, oldest first."""
        return await self._acknowledgements.list_for_alert(alert_id)

    async def get_first_for_alert(self, alert_id: UUID) -> AlertAcknowledgement | None:
        """Return *alert_id*'s own earliest acknowledgement (backs MTTA)."""
        return await self._acknowledgements.get_first_for_alert(alert_id)

    async def record(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        alert_id: UUID,
        acknowledgement_type: AcknowledgementType = AcknowledgementType.MANUAL,
        acknowledged_by: UUID | None,
        comment: str | None = None,
        resolution_notes: str | None = None,
        acknowledged_at: datetime | None = None,
    ) -> AlertAcknowledgement:
        """Record one acknowledgement for an alert."""
        return await self._acknowledgements.create(
            AlertAcknowledgement(
                organization_id=organization_id,
                project_id=project_id,
                alert_id=alert_id,
                acknowledgement_type=acknowledgement_type,
                acknowledged_by=acknowledged_by,
                comment=comment,
                resolution_notes=resolution_notes,
                acknowledged_at=acknowledged_at or datetime.now(UTC),
            )
        )


__all__ = ["AlertAcknowledgementService"]
