"""``plugin_manifests``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ManifestValidationStatus


class PluginManifestEntry(BaseModel):
    """``plugin_manifests`` -- one version's own manifest content snapshot.

    Named ``PluginManifestEntry``, not ``PluginManifest``, so it is never
    confused with ``shared_core.plugins.manifest.PluginManifest`` -- that
    dataclass covers only a subset of the fields docs/059's own "PLUGIN
    MANIFEST" section requires (no Publisher, no split Category+Type, no
    structured multi-platform Supported-Platform-Versions, no plural
    Entry Points, no API Requirements, no Health Checks, no Checksum), so
    this service keeps its own richer, DB-persisted manifest shape and
    validates it with its own engine (``app/manifests/``) rather than
    aliasing the framework's.
    """

    __tablename__ = "plugin_manifests"
    __table_args__ = (
        UniqueConstraint("plugin_version_id", name="uq_plugin_manifest_version"),
        Index("ix_plugin_manifest_status", "validation_status"),
    )

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    plugin_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugin_versions.id", ondelete="CASCADE"), index=True
    )
    raw_content: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """The manifest exactly as submitted -- name/publisher/category/type/
    version/supported-platform-versions/entry-points/permissions/
    dependencies/api-requirements/health-checks/checksum, per docs/059."""
    publisher_name: Mapped[str | None] = mapped_column(String(128), default=None)
    checksum: Mapped[str | None] = mapped_column(String(128), default=None)
    validation_status: Mapped[ManifestValidationStatus] = mapped_column(
        String(16), default=ManifestValidationStatus.PENDING, index=True
    )
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PluginManifestEntry"]
