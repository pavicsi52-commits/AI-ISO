"""Request/response schemas for ``/validations`` and ``/validation-profiles``.

Both routers front the same underlying
:class:`~app.services.profile.ValidationProfileService` -- docs/043's
own literal REST APIs list names both ``/validations`` (full CRUD plus
``execute``/``cancel``) and ``/validation-profiles`` (``GET``/``POST``
only) for what is, on every field and every acceptance-criteria line,
the same "reusable, named collection of checks" concept
(``ValidationProfile``) docs/043's own "VALIDATION PROFILES" section
describes exactly once. Rather than inventing a second, fake resource
type to justify two different underlying models, ``/validations`` is
implemented as the full lifecycle resource (matching
``services/workflow-runtime-service``'s own ``/workflows``) and
``/validation-profiles`` is a second, lighter list/create surface over
that identical resource -- every literal path in the doc is honored,
with no invented semantics neither path's own doc wording actually
supports.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ValidationConcurrencyStrategy,
    ValidationProfileType,
    ValidationTargetType,
)


class ValidationProfileCreateRequest(BaseModel):
    """Body of ``POST /validations`` / ``POST /validation-profiles``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    profile_type: ValidationProfileType
    target_types: list[ValidationTargetType] = Field(default_factory=list)
    check_ids: list[UUID] = Field(default_factory=list)
    concurrency_strategy: ValidationConcurrencyStrategy = ValidationConcurrencyStrategy.SEQUENTIAL
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    owner: str | None = Field(default=None, max_length=255)


class ValidationProfileUpdateRequest(BaseModel):
    """Body of ``PUT /validations/{id}`` -- always bumps ``current_version_number``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    target_types: list[ValidationTargetType] = Field(default_factory=list)
    check_ids: list[UUID] = Field(default_factory=list)
    concurrency_strategy: ValidationConcurrencyStrategy = ValidationConcurrencyStrategy.SEQUENTIAL
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    owner: str | None = Field(default=None, max_length=255)


class ValidationProfileResponse(BaseModel):
    """One reusable validation profile."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    description: str | None
    profile_type: ValidationProfileType
    target_types: list[str]
    check_ids: list[str]
    concurrency_strategy: str
    scoring_weights: dict[str, Any]
    tags: list[str]
    owner: str | None
    current_version_number: str


__all__ = [
    "ValidationProfileCreateRequest",
    "ValidationProfileResponse",
    "ValidationProfileUpdateRequest",
]
