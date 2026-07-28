"""``report_recipients`` table -- who a report goes to."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DistributionChannel, ExportFormat


class ReportRecipient(BaseModel):
    """One standing recipient of a report job.

    ``target`` is channel-dependent -- an address for email, a URL for
    webhook, a user id for in-app -- and validated per channel by
    :mod:`app.validators.distribution` rather than being split into a
    column per channel that is null for every other one.
    """

    __tablename__ = "report_recipients"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_jobs.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[DistributionChannel] = mapped_column(String(16), index=True)
    target: Mapped[str] = mapped_column(String(1024))
    export_format: Mapped[ExportFormat] = mapped_column(String(16), default=ExportFormat.PDF)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


__all__ = ["ReportRecipient"]
