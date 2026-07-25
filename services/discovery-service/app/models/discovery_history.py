"""``discovery_history`` table -- a human-readable narrative timeline
per job, distinct from ``discovery_audit`` (privileged-action audit
trail) -- the same "narrative feed vs. audit trail" split
``services/inventory-service``'s own ``asset_history``/
``inventory_audit`` pair established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class DiscoveryHistoryEntry(BaseModel):
    """One narrative timeline entry for a discovery job."""

    __tablename__ = "discovery_history"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["DiscoveryHistoryEntry"]
