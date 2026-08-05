"""``api_transformations`` -- one request or response transformation rule."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import TransformationDirection, TransformationKind


class ApiTransformationRule(BaseModel):
    """``api_transformations`` -- one rule applied to matching requests or responses."""

    __tablename__ = "api_transformations"
    __table_args__ = (Index("ix_api_transformation_org_route", "organization_id", "route_id"),)

    route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_routes.id", ondelete="CASCADE"), default=None, index=True
    )
    """``None`` applies globally, to every route."""

    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[TransformationKind] = mapped_column(String(32), index=True)
    direction: Mapped[TransformationDirection] = mapped_column(
        String(16), default=TransformationDirection.REQUEST
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Shape depends on :attr:`kind` -- e.g. for ``HEADER``:
    ``{"add": {...}, "remove": [...]}``; for ``URL_REWRITE``:
    ``{"pattern": ..., "replacement": ...}``."""

    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ApiTransformationRule"]
