"""``api_clients`` -- one registered API consumer.

Per this prompt's own OBJECTIVE, a client is "a web application, mobile
application, SDK, CLI tool, AI agent, automation system, partner
integration, or third-party API."
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ClientKind


class ApiClient(BaseModel):
    """``api_clients`` -- one registered caller of this gateway."""

    __tablename__ = "api_clients"

    name: Mapped[str] = mapped_column(String(128), index=True)
    client_kind: Mapped[ClientKind] = mapped_column(String(32), default=ClientKind.THIRD_PARTY)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    contact_email: Mapped[str | None] = mapped_column(String(255), default=None)

    default_rate_limit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_rate_limits.id", ondelete="SET NULL"), default=None
    )
    default_quota_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_quotas.id", ondelete="SET NULL"), default=None
    )

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ApiClient"]
