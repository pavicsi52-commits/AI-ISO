"""Request/response schemas for ``/alert-escalation-policies``.

Docs/045's own literal REST list names no escalation-policy endpoint,
yet "Escalation" is an explicit ACCEPTANCE CRITERIA line and
``POST /alerts/{id}/escalate`` (which the doc *does* name) has nothing
to walk without a stored policy. Added directly, the same "required
capability, no REST list entry" precedent every prior AI-IOS service
has established at least once.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import EscalationTargetType


class EscalationLevelRequest(BaseModel):
    """One level in a policy's own ordered chain.

    ``delay_seconds`` is measured from the *previous* level (cumulative
    down the chain), so "page on-call after 5 minutes, then their
    manager 10 minutes later" is written as ``300`` then ``600``.
    """

    target_type: EscalationTargetType
    target_reference: str = Field(min_length=1, max_length=255)
    delay_seconds: float = Field(ge=0)


class EscalationPolicyCreateRequest(BaseModel):
    """Body of ``POST /alert-escalation-policies``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    levels: list[EscalationLevelRequest] = Field(default_factory=list)
    enabled: bool = True


class EscalationLevelResponse(BaseModel):
    """One validated level, with its own resolved cumulative delay."""

    sequence: int
    target_type: EscalationTargetType
    target_reference: str
    delay_seconds: float
    cumulative_delay_seconds: float


class EscalationPolicyResponse(BaseModel):
    """One escalation policy."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    levels: list[EscalationLevelResponse]
    enabled: bool


__all__ = [
    "EscalationLevelRequest",
    "EscalationLevelResponse",
    "EscalationPolicyCreateRequest",
    "EscalationPolicyResponse",
]
