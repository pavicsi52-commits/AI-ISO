"""``validation_result_details`` table -- the raw collected data points
backing one :class:`~app.models.validation_result.ValidationResult`
(e.g. ``{"key": "disk_usage_percent", "value": 92.5}``), kept as
individual rows rather than one JSON blob on the result itself so a
single collector's own multi-metric output (e.g. one connectivity
check reporting latency, packet loss, and port state together) can be
queried, displayed, and trended independently.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class ValidationResultDetail(BaseModel):
    """One raw collected data point backing a validation result."""

    __tablename__ = "validation_result_details"

    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_results.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[Any] = mapped_column(JSON)


__all__ = ["ValidationResultDetail"]
