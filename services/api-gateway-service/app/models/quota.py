"""``api_quotas`` -- one configured quota, with its own live usage counter."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import QuotaKind, QuotaPeriod, QuotaScope


class ApiQuotaPolicy(BaseModel):
    """``api_quotas`` -- one quota and how much of it has been used this period."""

    __tablename__ = "api_quotas"

    scope: Mapped[QuotaScope] = mapped_column(String(16), index=True)
    scope_reference: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    kind: Mapped[QuotaKind] = mapped_column(String(16), default=QuotaKind.REQUEST)
    period: Mapped[QuotaPeriod] = mapped_column(String(16), default=QuotaPeriod.DAILY)

    limit_value: Mapped[float] = mapped_column(Float)
    used_value: Mapped[float] = mapped_column(Float, default=0.0)

    period_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_resets_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ApiQuotaPolicy"]
