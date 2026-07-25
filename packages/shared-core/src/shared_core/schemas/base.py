"""Base Pydantic schema every AI-IOS request/response model inherits."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Strict base schema: rejects unknown fields, validates on assignment."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )
