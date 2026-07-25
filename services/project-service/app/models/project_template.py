"""``project_templates`` table. Per docs/034 "PROJECT TEMPLATES": reusable
project templates (Infrastructure/Automation/Validation/Industrial/
Cloud/Hybrid/Custom projects), Template Versioning.

**Scope decision**: docs/034's own REST list names
``GET/POST /projects/templates`` -- not ``/projects/{id}/templates`` --
so a template is *not* scoped to one specific project the way every
other child table in this service is. It's scoped one tenant level up,
to the inherited (mandatory) ``organization_id`` column instead, the
same bare-UUID reference every AI-IOS service other than
organization-service itself uses. ``project_id`` is therefore left at
its mixin default here (nullable, unused) rather than overridden --
the one child table in this service that is *not* keyed to a specific
project.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProjectTemplateCategory


class ProjectTemplate(BaseModel):
    """One reusable, versioned project template."""

    __tablename__ = "project_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name", "template_version", name="uq_project_template_version"
        ),
    )

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    category: Mapped[ProjectTemplateCategory] = mapped_column(
        String(16), default=ProjectTemplateCategory.CUSTOM
    )
    # Named `template_version`, not `version` -- `version` is already the
    # inherited optimistic-locking counter every BaseModel entity carries
    # (shared_core.base.version_mixin.VersionMixin), a genuine naming
    # collision mypy's strict base-class checking caught immediately.
    template_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ProjectTemplate"]
