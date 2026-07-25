"""Request/response schemas for ``/policies``.

Per docs/032 "POLICY ENGINE": a policy's conditions and its initial
subject assignment are created together with the policy itself --
docs/032's REST list has no separate ``/policy-conditions`` or
``/policy-assignments`` surface, so both are embedded in the create
request.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    PermissionAction,
    PolicyConditionType,
    PolicyEffect,
    PolicyStatus,
    ResourceType,
    SubjectType,
)


class PolicyConditionInput(BaseModel):
    """One condition attached to a policy, in a create/update request."""

    condition_type: PolicyConditionType
    field: str | None = None
    operator: str = "equals"
    value: Any = None


class PolicyCreateRequest(BaseModel):
    """Body of ``POST /policies``."""

    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    effect: PolicyEffect = PolicyEffect.ALLOW
    resource_type: ResourceType | None = None
    action: PermissionAction | None = None
    priority: int = 100
    conditions: list[PolicyConditionInput] = Field(default_factory=list)
    subject_type: SubjectType = SubjectType.GLOBAL
    subject_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyUpdateRequest(BaseModel):
    """Body of ``PUT /policies/{id}``."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    effect: PolicyEffect = PolicyEffect.ALLOW
    resource_type: ResourceType | None = None
    action: PermissionAction | None = None
    priority: int = 100
    status: PolicyStatus = PolicyStatus.ACTIVE
    conditions: list[PolicyConditionInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyConditionResponse(BaseModel):
    """One condition attached to a policy, as returned by the API."""

    id: UUID
    condition_type: PolicyConditionType
    field: str | None
    operator: str
    value: Any


class PolicyResponse(BaseModel):
    """One policy, in full, with its conditions."""

    id: UUID
    name: str
    code: str
    description: str | None
    effect: PolicyEffect
    resource_type: ResourceType | None
    action: PermissionAction | None
    priority: int
    status: PolicyStatus
    conditions: list[PolicyConditionResponse]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = [
    "PolicyConditionInput",
    "PolicyConditionResponse",
    "PolicyCreateRequest",
    "PolicyResponse",
    "PolicyUpdateRequest",
]
