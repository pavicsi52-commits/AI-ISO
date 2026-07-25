"""``project_settings`` table. Per docs/034 "PROJECT SETTINGS": Default
Environment, Default Connector, Default Workflow Runtime, Notification
Settings, Retention Policies, Execution Policies, Automation Policies,
Validation Policies, Monitoring Policies, AI Settings, Storage
Policies, Security Policies.

Every child table in this service reuses its inherited ``project_id``
column (per :class:`shared_core.base.tenant_mixin.TenantMixin`) as the
*real* foreign key back to the owning :class:`~app.models.project.Project`
row, overridden here to non-nullable (the mixin declares it nullable by
default, since not every AI-IOS entity is project-scoped) plus an
explicit ``ForeignKey`` -- see ``app/models/project.py``'s own
docstring for the full self-referential-root-entity rationale this
mirrors from ``services/organization-service``.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectSettings(BaseModel):
    """One project's environment/execution/automation/security policy set."""

    __tablename__ = "project_settings"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_settings_project"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    default_environment: Mapped[str | None] = mapped_column(String(64), default=None)
    default_connector_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    default_workflow_runtime: Mapped[str | None] = mapped_column(String(64), default=None)
    notification_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retention_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    automation_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    monitoring_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ai_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    storage_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    security_policies: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ProjectSettings"]
