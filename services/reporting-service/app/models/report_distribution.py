"""``report_distribution`` table -- one delivery attempt of one export."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DistributionChannel, DistributionStatus


class ReportDistribution(BaseModel):
    """One delivery attempt.

    Every attempt is its own row, including failures. A delivery that
    silently vanished is indistinguishable from one never attempted,
    and "was the compliance report actually sent?" has to be answerable
    from the record.

    ``share_token``/``expires_at`` back docs/047's "Secure Expiration
    Links": the token is what a recipient presents, and an expired one
    stops working without anything having to delete the row.
    """

    __tablename__ = "report_distribution"

    export_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_exports.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_recipients.id", ondelete="SET NULL"), default=None, index=True
    )
    channel: Mapped[DistributionChannel] = mapped_column(String(16), index=True)
    target: Mapped[str] = mapped_column(String(1024))
    status: Mapped[DistributionStatus] = mapped_column(
        String(16), default=DistributionStatus.PENDING, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    share_token: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    storage_uri: Mapped[str | None] = mapped_column(String(1024), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ReportDistribution"]
