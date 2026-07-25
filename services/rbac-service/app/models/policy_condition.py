"""``policy_conditions`` table.

Per docs/032 "POLICY ENGINE": Conditional Access, Time-Based Access,
Location-Based Access, IP-Based Access, Custom Rules. Each row is one
condition attached to a policy; a policy with multiple conditions
requires all of them to hold (AND semantics), matching
``shared_core.security.policies.PolicyEngine.evaluate``'s own
all-registered-policies-must-pass behavior.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import PolicyConditionType


class PolicyCondition(BaseModel):
    """One evaluable condition attached to an :class:`AuthorizationPolicy`."""

    __tablename__ = "policy_conditions"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("authorization_policies.id", ondelete="CASCADE")
    )
    condition_type: Mapped[PolicyConditionType] = mapped_column(String(32))
    field: Mapped[str | None] = mapped_column(String(128), default=None)
    operator: Mapped[str] = mapped_column(String(32), default="equals")
    value: Mapped[Any | None] = mapped_column(JSON, default=None)


__all__ = ["PolicyCondition"]
