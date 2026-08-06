"""``webhook_transformations`` -- payload/header transformation rules."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import TransformationKind


class WebhookTransformation(BaseModel):
    """``webhook_transformations`` -- one endpoint's own outbound-payload transformation rule."""

    __tablename__ = "webhook_transformations"
    __table_args__ = (Index("ix_webhook_transformation_endpoint", "endpoint_id"),)

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[TransformationKind] = mapped_column(String(32), index=True)
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["WebhookTransformation"]
