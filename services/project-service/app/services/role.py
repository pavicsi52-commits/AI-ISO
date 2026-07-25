"""Project role management.

Per docs/034 "PROJECT ROLES": Owner, Administrator, Operator,
Automation Engineer, Validation Engineer, Developer, Viewer, Auditor,
**Custom Roles**. See ``app/models/project_role.py``'s own docstring
for the full design rationale (a dynamic, persisted catalog rather than
a fixed enum, with self-contained rank-based hierarchy enforcement
instead of a live call to ``services/rbac-service``).
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.not_found import NotFoundError

from app.models.project_role import SYSTEM_ROLE_RANKS, ProjectRole
from app.repositories.project_role import ProjectRoleRepository


class ProjectRoleService:
    """Looks up, lists, and creates custom project roles."""

    def __init__(self, roles: ProjectRoleRepository) -> None:
        self._roles = roles

    async def get_by_code(self, project_id: UUID, code: str) -> ProjectRole:
        """Return the role identified by *code*, visible to *project_id*.

        Raises:
            NotFoundError: If no such role (system or that project's own
                custom role) exists.
        """
        role = await self._roles.get_by_code(project_id, code)
        if role is None:
            raise NotFoundError(f"Role {code!r} was not found for this project.")
        return role

    async def get_by_id(self, role_id: UUID) -> ProjectRole:
        """Return the role identified by *role_id*.

        Raises:
            NotFoundError: If no such role exists.
        """
        return await self._roles.require_by_id(role_id)

    async def list_available(self, project_id: UUID) -> list[ProjectRole]:
        """Every role visible to *project_id*: every system role, plus that
        project's own custom roles.
        """
        return await self._roles.list_available_for_project(project_id)

    async def create_custom(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        name: str,
        code: str,
        rank: int,
        description: str | None,
    ) -> ProjectRole:
        """Create a custom role scoped to *project_id* ("Custom Roles").

        Raises:
            BusinessRuleError: If *rank* would meet or exceed the Owner
                system role's rank -- a custom role may never outrank
                the built-in ownership tier.
        """
        if rank >= SYSTEM_ROLE_RANKS["owner"]:
            raise BusinessRuleError(
                "A custom role's rank must be lower than the system Owner role's rank."
            )
        return await self._roles.create(
            ProjectRole(
                project_id=project_id,
                organization_id=organization_id,
                name=name,
                code=code,
                rank=rank,
                is_system=False,
                description=description,
            )
        )


__all__ = ["ProjectRoleService"]
