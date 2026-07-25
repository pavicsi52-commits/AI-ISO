"""``project_labels`` table -- structured ``key:value`` labels on a
project, distinct from :class:`~app.models.project_tag.ProjectTag`'s
free-form single-string tags. Docs/034's own "PROJECT TAGS" section
folds "Labels" in alongside "Custom Tags" and "Categories" without
further detail; this service models them as the common enterprise
distinction (Kubernetes-style ``key: value`` pairs, as opposed to a
tag's single free-form string) since ``project_tags`` and
``project_labels`` are named as two separate tables in docs/034's own
"DATABASE TABLES" list -- a single, undifferentiated shape would leave
one of the two tables redundant.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectLabel(BaseModel):
    """One ``key: value`` label assigned to a project."""

    __tablename__ = "project_labels"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_project_label_key"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(512))
    color: Mapped[str | None] = mapped_column(String(16), default=None)


__all__ = ["ProjectLabel"]
