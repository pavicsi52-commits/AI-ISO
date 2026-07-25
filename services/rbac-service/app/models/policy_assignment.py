"""``policy_assignments`` table -- binds a policy to who it applies to.

Per docs/032 "POLICY ENGINE"/"POLICY ASSIGNMENTS". ``subject_id`` is
``None`` only when ``subject_type`` is
:attr:`~app.models.enums.SubjectType.GLOBAL` (the policy applies to
every evaluation of its resource/action, not one particular user/role).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SubjectType


class PolicyAssignment(BaseModel):
    """One binding of an :class:`~app.models.authorization_policy.AuthorizationPolicy`
    to a subject.
    """

    __tablename__ = "policy_assignments"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("authorization_policies.id", ondelete="CASCADE")
    )
    subject_type: Mapped[SubjectType] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["PolicyAssignment"]
