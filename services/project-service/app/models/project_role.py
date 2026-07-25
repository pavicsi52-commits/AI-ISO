"""``project_roles`` table. Per docs/034 "PROJECT ROLES": Owner,
Administrator, Operator, Automation Engineer, Validation Engineer,
Developer, Viewer, Auditor, **Custom Roles**. "Integrate with Prompt 032."

**Design decision**: a plain fixed enum (the shape
``services/organization-service`` uses for its own three-value
``MemberRole``) cannot represent "Custom Roles", which docs/034
explicitly requires. This is instead a genuinely dynamic, persisted
role catalog -- closer in spirit to ``services/rbac-service``'s own
dynamic role model -- but, matching the precedent
``services/organization-service`` already established for its own
identical "Integrate with Prompt 032" instruction, authorization is
still enforced *within this service*, via each role's numeric ``rank``
(see ``app/projects/membership.py::role_at_least()``), rather than a
live HTTP call out to ``services/rbac-service`` for every request.
Introducing that cross-service-calling convention was judged
higher-risk than the value of delegating a rank comparison this
service can already make correctly and fast.

Eight **system** roles (``project_id IS NULL``, ``is_system=True``) are
seeded with fixed, deterministic ids by this service's own seed
migration, mirroring ``services/rbac-service``'s deterministic system
role/permission ids -- every AI-IOS deployment's "Owner" project role is
the same row identity. A project may additionally define its own
**custom** roles (``project_id`` set to that project, ``is_system=False``),
each carrying its own ``rank`` so it slots correctly into the same
hierarchy comparison custom or system roles alike.

``project_id`` is deliberately *not* overridden to non-nullable here
(unlike every other child table in this service) since a system role
must be usable by every project, not owned by exactly one -- the same
"optional FK" shape ``services/organization-service``'s own
``OrganizationMember.department_id``/``business_unit_id``/``team_id``
already established.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectRole(BaseModel):
    """One project role: a system-wide default, or a project's own custom role."""

    __tablename__ = "project_roles"
    __table_args__ = (
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        UniqueConstraint("project_id", "code", name="uq_project_role_code"),
    )

    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)


# Fixed, deterministic system-role ids -- seeded once by this service's
# own seed migration, referenced directly by app code wherever a system
# role must be assigned without a lookup-by-code round trip (e.g. making
# a project's creator its Owner).
SYSTEM_ROLE_IDS: dict[str, uuid.UUID] = {
    "owner": uuid.UUID("00000000-0000-0000-0000-000000000201"),
    "administrator": uuid.UUID("00000000-0000-0000-0000-000000000202"),
    "operator": uuid.UUID("00000000-0000-0000-0000-000000000203"),
    "automation_engineer": uuid.UUID("00000000-0000-0000-0000-000000000204"),
    "validation_engineer": uuid.UUID("00000000-0000-0000-0000-000000000205"),
    "developer": uuid.UUID("00000000-0000-0000-0000-000000000206"),
    "viewer": uuid.UUID("00000000-0000-0000-0000-000000000207"),
    "auditor": uuid.UUID("00000000-0000-0000-0000-000000000208"),
}

SYSTEM_ROLE_RANKS: dict[str, int] = {
    "owner": 100,
    "administrator": 90,
    "operator": 50,
    "automation_engineer": 50,
    "validation_engineer": 50,
    "developer": 40,
    "viewer": 10,
    "auditor": 10,
}

OWNER_ROLE_ID = SYSTEM_ROLE_IDS["owner"]
ADMINISTRATOR_ROLE_ID = SYSTEM_ROLE_IDS["administrator"]
ADMINISTRATOR_RANK = SYSTEM_ROLE_RANKS["administrator"]
MEMBER_RANK = 0

__all__ = [
    "ADMINISTRATOR_RANK",
    "ADMINISTRATOR_ROLE_ID",
    "MEMBER_RANK",
    "OWNER_ROLE_ID",
    "SYSTEM_ROLE_IDS",
    "SYSTEM_ROLE_RANKS",
    "ProjectRole",
]
