"""Discovery result recording and lookup. Backs ``GET /discovery/results``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.discovery_result import DiscoveryResult
from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.repositories.discovery_result import DiscoveryResultRepository


class DiscoveryResultService:
    """Records and lists raw protocol-probe outcomes."""

    def __init__(self, results: DiscoveryResultRepository) -> None:
        self._results = results

    async def record(
        self,
        job_id: UUID,
        target_id: UUID,
        *,
        organization_id: UUID,
        protocol: ProtocolType,
        status: DiscoveryResultStatus,
        latency_ms: float | None,
        raw_data: dict[str, Any],
        error_message: str | None,
    ) -> DiscoveryResult:
        """Record one protocol probe's outcome."""
        return await self._results.create(
            DiscoveryResult(
                job_id=job_id,
                target_id=target_id,
                organization_id=organization_id,
                protocol=protocol,
                status=status,
                latency_ms=latency_ms,
                raw_data=raw_data,
                error_message=error_message,
                executed_at=datetime.now(UTC),
            )
        )

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryResult]:
        """Every probe result recorded for *job_id*."""
        return await self._results.list_for_job(job_id)


__all__ = ["DiscoveryResultService"]
