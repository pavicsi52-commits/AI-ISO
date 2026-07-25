"""``automation_variables`` table. Per docs/040 "WORKFLOW INTEGRATION"
"Shared Variables" plus the general need to scope a reusable variable
beyond one execution -- the same scoped-variable shape
``services/configuration-management-service``'s own
``ConfigurationVariable`` established.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import VariableScope


class AutomationVariable(BaseModel):
    """One scoped automation variable."""

    __tablename__ = "automation_variables"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope", "scope_ref_id", "key", name="uq_automation_variable_key"
        ),
    )

    scope: Mapped[VariableScope] = mapped_column(String(16), index=True)
    scope_ref_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[str | None] = mapped_column(String(4096), default=None)
    is_secret_reference: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["AutomationVariable"]
