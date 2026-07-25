"""``configuration_policies`` table. Per docs/039 "POLICIES" "Support":
Naming Policies, Version Policies, Approval Policies, Compliance
Policies, Deployment Policies, Retention Policies, Environment
Policies.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PolicyType


class ConfigurationPolicy(BaseModel):
    """One governance policy enforced against configuration profiles."""

    __tablename__ = "configuration_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_configuration_policy_name"),
    )

    policy_type: Mapped[PolicyType] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enforced: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ConfigurationPolicy"]
