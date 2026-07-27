"""``validation_profiles`` table -- a reusable, named collection of
checks applied together against one or more targets.

``check_ids`` composes a profile out of the standalone, reusable
``validation_checks`` catalog via a JSON array of string ids rather
than a join table -- the same "reusable content referenced by id, not
owned" shape ``WorkflowVersion.nodes``/``.edges`` already established
for a DAG referencing node/edge definitions, chosen here because
docs/043's own 17-table DATABASE TABLES list has no
``validation_profile_checks`` join table. Ids are stored as ``str``,
not ``uuid.UUID``, the same way ``WorkflowCheckpoint.completed_node_ids``
already does -- the stdlib ``json`` encoder SQLAlchemy's generic
``JSON`` type uses cannot serialize a raw ``uuid.UUID`` value.
``current_version_number`` is a bumped-on-update string (docs/043's
own "Versioning" support), not a separate version-row-per-change table
like ``WorkflowVersion`` -- no such table is named in the 17-table
list either, matching the lighter-weight precedent ``AutomationJob``'s
own versioning already established over ``WorkflowVersion``'s heavier
one.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationConcurrencyStrategy, ValidationProfileType


class ValidationProfile(BaseModel):
    """A reusable, named collection of checks applied together."""

    __tablename__ = "validation_profiles"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    profile_type: Mapped[ValidationProfileType] = mapped_column(String(24), index=True)
    target_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    check_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    concurrency_strategy: Mapped[ValidationConcurrencyStrategy] = mapped_column(
        String(16), default=ValidationConcurrencyStrategy.SEQUENTIAL
    )
    scoring_weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner: Mapped[str | None] = mapped_column(String(255), default=None)
    current_version_number: Mapped[str] = mapped_column(String(32), default="1.0.0")


__all__ = ["ValidationProfile"]
