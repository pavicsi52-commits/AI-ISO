"""Long-running job response payload."""

from __future__ import annotations

from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.schemas.base import BaseSchema


class JobResponse(BaseSchema):
    """Payload for long-running-operation endpoints (docs/006_API_Design_Master.md.txt
    "LONG RUNNING TASKS"). Clients poll ``/jobs/{job_id}`` using this shape."""

    job_id: UUID
    status: JobStatus
