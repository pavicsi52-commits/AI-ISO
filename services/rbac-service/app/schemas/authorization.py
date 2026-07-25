"""Request/response schemas for ``POST /authorization/evaluate``.

Per docs/032 "AUTHORIZATION EVALUATION": Evaluate User, Role,
Permissions, Policies, Conditions, Resource Ownership, Tenant,
Environment. Return: Decision (Allow/Deny), Reason.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AuthorizationDecision, PermissionAction, ResourceType


class EvaluateRequest(BaseModel):
    """One authorization question: can *user_id* *action* *resource_type*[/*resource_id*]?"""

    user_id: UUID
    action: PermissionAction
    resource_type: ResourceType
    resource_id: UUID | None = None
    organization_id: UUID | None = None
    project_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    """The decision for one :class:`EvaluateRequest`."""

    decision: AuthorizationDecision
    reason: str
    matched_permission_code: str | None = None
    matched_policy_code: str | None = None
    evaluated_at: datetime

    @property
    def allowed(self) -> bool:
        """``True`` iff :attr:`decision` is :attr:`AuthorizationDecision.ALLOW`."""
        return self.decision == AuthorizationDecision.ALLOW


__all__ = ["EvaluateRequest", "EvaluateResponse"]
