"""Request/response schemas for ``/discovery/jobs``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from shared_core.enums.job_status import JobStatus

from app.models.enums import DiscoveryMode


class DiscoveryJobCreateRequest(BaseModel):
    """Body of ``POST /discovery/jobs`` -- re-runs *profile_id* against
    every :class:`~app.models.discovery_target.DiscoveryTarget` already
    registered under it (accumulated as a side effect of prior
    ``/discovery/*-scan`` calls naming this same ``profile_id``), the
    "repeat/refresh a known set of targets" counterpart to the
    ``/discovery/*-scan`` endpoints' "ad-hoc, one-shot, define targets
    inline" shape. This is also what
    ``app/scheduling/registrar.py``-registered recurring schedules
    trigger internally.
    """

    organization_id: UUID
    profile_id: UUID
    mode: DiscoveryMode = DiscoveryMode.SCHEDULED


class DiscoveryJobResponse(BaseModel):
    """One discovery job's status and result summary."""

    id: UUID
    organization_id: UUID
    profile_id: UUID | None
    schedule_id: UUID | None
    mode: DiscoveryMode
    status: JobStatus
    triggered_by: UUID | None
    total_targets: int
    succeeded_targets: int
    failed_targets: int
    discovered_asset_count: int
    discovered_relationship_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None


__all__ = ["DiscoveryJobCreateRequest", "DiscoveryJobResponse"]
