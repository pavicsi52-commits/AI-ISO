"""``automation_jobs`` table -- the reusable automation job definition.

Per docs/040 "AUTOMATION TYPES"/"PLAYBOOK SUPPORT"/"EXECUTION MODES":
a job is a *definition* (what to run, how, against what) that can be
executed one or many times; one execution of it is a separate
:class:`~app.models.automation_execution.AutomationExecution` row, the
same definition/run split
``services/configuration-management-service``'s own
``ConfigurationProfile``/``ConfigurationVersion`` pair established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AutomationType, ExecutionMode, JobStatus, PlaybookType


class AutomationJob(BaseModel):
    """One reusable automation job definition."""

    __tablename__ = "automation_jobs"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    automation_type: Mapped[AutomationType] = mapped_column(String(32), index=True)
    playbook_type: Mapped[PlaybookType] = mapped_column(String(32), index=True)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.DRAFT, index=True)
    execution_mode: Mapped[ExecutionMode] = mapped_column(String(24), default=ExecutionMode.MANUAL)
    content: Mapped[str] = mapped_column(Text)
    target_selector: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["AutomationJob"]
