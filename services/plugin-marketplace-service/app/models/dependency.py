"""``plugin_dependencies``."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PluginDependency(BaseModel):
    """``plugin_dependencies`` -- one dependency edge, ``plugin`` -> ``depends_on``.

    A DB-backed graph spanning organizations -- distinct from
    ``shared_core.plugins.resolver.DependencyResolver``, which only
    ever walks an in-memory ``dict[str, PluginManifest]`` for one
    already-loaded process. ``app/dependencies/`` runs its own real DFS
    cycle check over rows in this table, mirroring
    ``playbook-service/app/services/dependency.py``'s
    ``PlaybookDependencyService._creates_cycle``.
    """

    __tablename__ = "plugin_dependencies"
    __table_args__ = (
        UniqueConstraint("plugin_id", "depends_on_plugin_id", name="uq_plugin_dependency_edge"),
        Index("ix_plugin_dependency_depends_on", "depends_on_plugin_id"),
    )

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    depends_on_plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    version_constraint: Mapped[str] = mapped_column(String(64), default="*")
    """A ``shared_core.plugins.versioning``-compatible specifier the
    dependency's own installed version must satisfy."""
    optional: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["PluginDependency"]
