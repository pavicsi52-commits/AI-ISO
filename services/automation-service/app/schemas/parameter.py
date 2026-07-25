"""Request/response schemas for automation job input-parameter definitions."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class AutomationParameterCreateRequest(BaseModel):
    """Body of ``POST /automation/jobs/{id}/parameters``."""

    name: str = Field(min_length=1, max_length=255)
    parameter_type: str = Field(default="string", max_length=32)
    required: bool = False
    default_value: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=1024)


class AutomationParameterResponse(BaseModel):
    """One input-parameter definition for an automation job."""

    id: UUID
    job_id: UUID
    name: str
    parameter_type: str
    required: bool
    default_value: str | None
    description: str | None


__all__ = ["AutomationParameterCreateRequest", "AutomationParameterResponse"]
