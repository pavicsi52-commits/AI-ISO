"""Discovery failure recording -- used internally by
``app/services/discovery_execution.py``; has no REST surface of its own.
"""

from __future__ import annotations

from uuid import UUID

from app.models.discovery_failure import DiscoveryFailure
from app.models.enums import FailureReason, ProtocolType
from app.repositories.discovery_failure import DiscoveryFailureRepository


class DiscoveryFailureService:
    """Records and lists failed discovery probes for a job."""

    def __init__(self, failures: DiscoveryFailureRepository) -> None:
        self._failures = failures

    async def record(
        self,
        job_id: UUID,
        *,
        organization_id: UUID,
        target_id: UUID | None,
        protocol: ProtocolType,
        failure_reason: FailureReason,
        error_detail: str | None = None,
    ) -> DiscoveryFailure:
        """Record one failed discovery probe."""
        return await self._failures.create(
            DiscoveryFailure(
                job_id=job_id,
                organization_id=organization_id,
                target_id=target_id,
                protocol=protocol,
                failure_reason=failure_reason,
                error_detail=error_detail,
            )
        )

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryFailure]:
        """Every failed probe recorded for *job_id*."""
        return await self._failures.list_for_job(job_id)


__all__ = ["DiscoveryFailureService"]
