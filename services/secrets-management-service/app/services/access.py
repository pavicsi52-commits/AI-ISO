"""Secret access-control grants ("SECRET ACCESS": Read, Write, Rotate,
Delete, Export, Share, Lease, Restore).

Self-contained access-control-list resolution of docs/035's own
"Integrate with Prompt 032 RBAC" instruction -- the same
self-contained-ACL choice ``services/organization-service`` and
``services/project-service`` already made for their own equivalent
instructions, rather than a live HTTP call to ``services/rbac-service``.

This service only manages grants (create/update/revoke/list). The
actual allow/deny *decision* -- "is the secret's owner, or holds a
non-expired grant naming this action" -- lives in
``app/api/deps.py::require_secret_action``, which has access to both
this service and :class:`~app.services.secret.SecretService` (needed to
resolve ``owner_id``), matching
``services/project-service/app/api/deps.py::require_role_in_project``'s
identical "decision lives at the dependency layer" shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import SecretAccessAction
from app.models.secret_access import SecretAccessGrant
from app.repositories.secret_access import SecretAccessRepository


class SecretAccessService:
    """Grants, revokes, and checks secret access-control entries."""

    def __init__(self, access: SecretAccessRepository) -> None:
        self._access = access

    async def list_for_secret(self, secret_id: UUID) -> list[SecretAccessGrant]:
        """Every access grant on *secret_id*."""
        return await self._access.list_for_secret(secret_id)

    async def grant(
        self,
        secret_id: UUID,
        *,
        organization_id: UUID,
        principal_id: UUID,
        actions: list[SecretAccessAction],
        granted_by: UUID,
        expires_at: datetime | None = None,
    ) -> SecretAccessGrant:
        """Grant (or replace) *principal_id*'s actions on *secret_id*."""
        existing = await self._access.get_for_principal(secret_id, principal_id)
        if existing is not None:
            existing.actions = [action.value for action in actions]
            existing.granted_by = granted_by
            existing.expires_at = expires_at
            return existing
        return await self._access.create(
            SecretAccessGrant(
                secret_id=secret_id,
                organization_id=organization_id,
                principal_id=principal_id,
                actions=[action.value for action in actions],
                granted_by=granted_by,
                expires_at=expires_at,
            )
        )

    async def revoke(self, secret_id: UUID, principal_id: UUID) -> None:
        """Revoke *principal_id*'s grant on *secret_id*, if any (no-op otherwise)."""
        existing = await self._access.get_for_principal(secret_id, principal_id)
        if existing is not None:
            await self._access.delete(existing.id)

    async def has_action(
        self, secret_id: UUID, principal_id: UUID, action: SecretAccessAction
    ) -> bool:
        """Whether *principal_id* holds a non-expired grant naming *action*
        on *secret_id*. Does **not** account for ownership -- see the
        module docstring.
        """
        grant = await self._access.get_for_principal(secret_id, principal_id)
        if grant is None:
            return False
        if grant.expires_at is not None and grant.expires_at <= datetime.now(UTC):
            return False
        return action.value in grant.actions


__all__ = ["SecretAccessService"]
