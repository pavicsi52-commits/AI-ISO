"""``ai_tools`` table -- one registered callable tool ("TOOL CALLING").

``parameters_schema`` is the JSON Schema the model is shown and every
argument set is validated against before execution -- the structural
half of "Tool Permission Validation"/"Output Validation".
``required_permission`` names the RBAC permission a caller must hold;
a tool with none set is readable by any authenticated caller.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ToolKind


class AiTool(BaseModel):
    """One registered callable tool."""

    __tablename__ = "ai_tools"

    tool_key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    tool_kind: Mapped[ToolKind] = mapped_column(String(32), index=True)
    parameters_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    required_permission: Mapped[str | None] = mapped_column(String(128), default=None)
    is_mutating: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AiTool"]
