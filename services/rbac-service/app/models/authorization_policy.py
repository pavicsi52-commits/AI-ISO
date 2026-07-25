"""``authorization_policies`` table. Per docs/032 "POLICY ENGINE"."""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PermissionAction, PolicyEffect, PolicyStatus, ResourceType


class AuthorizationPolicy(BaseModel):
    """One named policy: an effect applied to a resource/action, evaluated
    alongside its :class:`~app.models.policy_condition.PolicyCondition` rows.
    """

    __tablename__ = "authorization_policies"

    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    effect: Mapped[PolicyEffect] = mapped_column(String(8), default=PolicyEffect.ALLOW)
    resource_type: Mapped[ResourceType | None] = mapped_column(String(32), default=None)
    action: Mapped[PermissionAction | None] = mapped_column(String(32), default=None)
    priority: Mapped[int] = mapped_column(default=100)
    status: Mapped[PolicyStatus] = mapped_column(String(16), default=PolicyStatus.ACTIVE)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["AuthorizationPolicy"]
