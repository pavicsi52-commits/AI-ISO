"""``configuration_variables`` table. Per docs/039 "CONFIGURATION
VARIABLES" "Support": Global Variables, Organization Variables,
Project Variables, Environment Variables, Asset Variables, Secrets
References, Runtime Variables, Computed Variables, Validation Rules.

``organization_id``/``project_id`` (inherited from
:class:`~shared_core.database.base.BaseModel`) already scope
``ORGANIZATION``/``PROJECT``-scoped rows; :attr:`scope_ref_id` covers
the remaining scopes that need a reference beyond tenant (an
``ENVIRONMENT`` name's own id, or an ``ASSET``'s managed-asset id) --
``GLOBAL``/``RUNTIME``/``COMPUTED`` need no reference at all.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import VariableScope


class ConfigurationVariable(BaseModel):
    """One scoped configuration variable."""

    __tablename__ = "configuration_variables"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope", "scope_ref_id", "key", name="uq_configuration_variable_key"
        ),
    )

    scope: Mapped[VariableScope] = mapped_column(String(24), index=True)
    scope_ref_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[str | None] = mapped_column(String(4096), default=None)
    is_secret_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    is_computed: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_rule: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["ConfigurationVariable"]
