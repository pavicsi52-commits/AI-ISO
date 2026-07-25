"""Request/response schemas for automation variables."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import VariableScope


class AutomationVariableCreateRequest(BaseModel):
    """Body of ``POST /automation/variables``."""

    organization_id: UUID
    scope: VariableScope
    scope_ref_id: UUID | None = None
    key: str = Field(min_length=1, max_length=255)
    value: str | None = Field(default=None, max_length=4096)
    is_secret_reference: bool = False


class AutomationVariableResponse(BaseModel):
    """One scoped automation variable."""

    id: UUID
    organization_id: UUID
    scope: VariableScope
    scope_ref_id: UUID | None
    key: str
    value: str | None
    is_secret_reference: bool


__all__ = ["AutomationVariableCreateRequest", "AutomationVariableResponse"]
