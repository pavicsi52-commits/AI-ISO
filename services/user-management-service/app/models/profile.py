"""``user_profiles`` table.

Per docs/031 "USER PROFILE": Personal Information, Contact
Information, Biography, Job Title, Department, Employee ID, Manager,
Profile Photo, Custom Fields.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class UserProfile(BaseModel):
    """Extended profile information for one user."""

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    biography: Mapped[str | None] = mapped_column(Text, default=None)
    job_title: Mapped[str | None] = mapped_column(String(255), default=None)
    department: Mapped[str | None] = mapped_column(String(255), default=None)
    employee_id: Mapped[str | None] = mapped_column(String(64), default=None)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    profile_photo: Mapped[str | None] = mapped_column(String(1024), default=None)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["UserProfile"]
