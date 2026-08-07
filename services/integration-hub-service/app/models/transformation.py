"""``connector_transformations``."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DataFormat, TransformationKind


class ConnectorTransformation(BaseModel):
    """``connector_transformations`` -- one payload-shaping rule attached to a connector."""

    __tablename__ = "connector_transformations"
    __table_args__ = (Index("ix_connector_transformation_connector", "connector_id"),)

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[TransformationKind] = mapped_column(String(24))
    source_format: Mapped[DataFormat] = mapped_column(String(8), default=DataFormat.JSON)
    target_format: Mapped[DataFormat] = mapped_column(String(8), default=DataFormat.JSON)
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ConnectorTransformation"]
