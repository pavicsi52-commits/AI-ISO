"""``connector_categories``, ``connectors``, and ``connector_versions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConnectorAuthMethod, ConnectorCategory, ConnectorLifecycleStatus


class ConnectorCategoryEntry(BaseModel):
    """``connector_categories`` -- the fifteen built-in categories, plus any custom ones."""

    __tablename__ = "connector_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_connector_category_name"),
    )

    name: Mapped[ConnectorCategory] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)


class Connector(BaseModel):
    """``connectors`` -- one organization's own registered connector instance.

    ``current_version_number`` -- not ``version``, which
    ``BaseEntityMixin`` already reserves for optimistic locking (the
    exact bug class this build has hit twice already; see
    ``ConnectorVersion.version_number`` below for the same reason).
    """

    __tablename__ = "connectors"
    __table_args__ = (Index("ix_connector_category", "category"),)

    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[ConnectorCategory] = mapped_column(String(32), index=True)
    connector_type: Mapped[str] = mapped_column(String(64), index=True)
    """Which catalog entry this is an instance of, e.g. ``"aws"``, ``"github"``,
    ``"custom"`` -- a free-text reference to ``ConnectorMarketplaceEntry.slug``,
    not a Python enum: docs/058's own "BUILT-IN CONNECTORS" list names
    dozens of them, too many for a closed enum, and ``CUSTOM`` connectors
    add caller-defined ones the catalog itself accepts freely."""
    marketplace_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connector_marketplace.id", ondelete="SET NULL"), default=None, index=True
    )
    current_version_number: Mapped[str | None] = mapped_column(String(32), default=None)
    status: Mapped[ConnectorLifecycleStatus] = mapped_column(
        String(16), default=ConnectorLifecycleStatus.REGISTERED, index=True
    )
    auth_method: Mapped[ConnectorAuthMethod] = mapped_column(
        String(24), default=ConnectorAuthMethod.API_KEY
    )
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """Connector-scoped configuration, including event-routing rules
    (``config["routing"]``) -- docs/058's own "DATABASE TABLES" section
    lists no dedicated routing-rule table, so routing configuration
    lives here rather than inventing one beyond the literal list."""
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)


class ConnectorVersion(BaseModel):
    """``connector_versions`` -- one connector instance's own upgrade/rollback history.

    Mirrors ``playbook-service``'s own ``PlaybookVersion.version_number``
    precedent -- an immutable snapshot per version, never named
    ``version`` for the same reserved-column reason as everywhere else
    in this column.
    """

    __tablename__ = "connector_versions"
    __table_args__ = (
        UniqueConstraint("connector_id", "version_number", name="uq_connector_version_number"),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[str] = mapped_column(String(32))
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    changelog: Mapped[str | None] = mapped_column(Text, default=None)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    installed_by: Mapped[str | None] = mapped_column(String(128), default=None)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["Connector", "ConnectorCategoryEntry", "ConnectorVersion"]
