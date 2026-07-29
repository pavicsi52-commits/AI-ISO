"""Dashboard sharing and access control ("SHARING", "SECURITY").

Access is decided in one place, :meth:`SharingService.resolve_access`,
so every route asks the same question the same way. Scattering the
rules across handlers is how a dashboard ends up readable through one
endpoint and not another.

**Access is deny-by-default.** An unknown dashboard, an expired share,
a revoked share, and a private dashboard belonging to someone else all
resolve to no access. The only ways in are: owning it, its being
published organization- or project-wide, an active directed share, an
active role permission, or a valid unexpired link token.

**Link tokens are returned exactly once.** The token is a bearer
credential for someone with no session, so it goes to its creator and
never appears in a listing -- the same rule
``services/reporting-service`` established for report links.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.events.dashboard_events import SOURCE_SERVICE, DashboardSharedEvent
from app.models.dashboard import Dashboard
from app.models.dashboard_permission import DashboardPermission
from app.models.dashboard_share import DashboardShare
from app.models.enums import DashboardVisibility, SharePermission
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_permission import DashboardPermissionRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.services.dashboard import visibility_of
from app.types import EventPublisher

_TOKEN_BYTES = 32
"""256 bits of entropy for a link token.

The token *is* the credential for an unauthenticated viewer, so it has
to be unguessable. ``secrets`` rather than ``random``: the latter is
seeded predictably and is not safe for anything security-bearing.
"""

_RANK: dict[SharePermission, int] = {
    SharePermission.VIEW: 1,
    SharePermission.EDIT: 2,
    SharePermission.MANAGE: 3,
}
"""Permission strength, so the *most* permissive grant wins.

A user who is both in a viewer role and directly granted edit should
get edit; taking whichever grant was found first would make access
depend on query order.
"""


def permission_of(value: SharePermission | str) -> SharePermission:
    """Normalise a permission that may have come back from Postgres as ``str``."""
    return value if isinstance(value, SharePermission) else SharePermission(value)


def new_share_token() -> str:
    """Generate an unguessable share-link token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


@dataclass(frozen=True, slots=True)
class Access:
    """The outcome of an access check."""

    allowed: bool
    permission: SharePermission | None = None
    reason: str | None = None

    @property
    def can_edit(self) -> bool:
        """Whether the caller may change the dashboard."""
        return self.allowed and self.permission in (
            SharePermission.EDIT,
            SharePermission.MANAGE,
        )

    @property
    def can_manage(self) -> bool:
        """Whether the caller may share or delete the dashboard."""
        return self.allowed and self.permission is SharePermission.MANAGE


DENIED = Access(allowed=False, reason="You do not have access to this dashboard.")
"""The single denial value, so every path denies identically."""


class SharingService:
    """Decides access and manages shares and role permissions."""

    def __init__(
        self,
        dashboards: DashboardRepository,
        shares: DashboardShareRepository,
        permissions: DashboardPermissionRepository,
        *,
        publish_event: EventPublisher,
        link_ttl_seconds: int = 604_800,
    ) -> None:
        self._dashboards = dashboards
        self._shares = shares
        self._permissions = permissions
        self._publish_event = publish_event
        self._link_ttl = link_ttl_seconds

    async def resolve_access(
        self,
        dashboard: Dashboard,
        *,
        user_id: UUID | None,
        roles: list[str] | None = None,
    ) -> Access:
        """Decide what *user_id* may do with *dashboard*.

        Every grant is considered and the strongest wins, so access does
        not depend on the order rules happen to be evaluated in.
        """
        if user_id is not None and dashboard.owner_id == user_id:
            return Access(allowed=True, permission=SharePermission.MANAGE)

        best: SharePermission | None = None
        visibility = visibility_of(dashboard)
        if visibility in (DashboardVisibility.ORGANIZATION, DashboardVisibility.PROJECT):
            best = SharePermission.VIEW

        if user_id is not None:
            for share in await self._shares.list_for_dashboard(dashboard.id, active_only=True):
                if share.shared_with_user_id != user_id or self._is_expired(share):
                    continue
                best = self._stronger(best, permission_of(share.permission))

        for role in roles or []:
            granted = await self._permissions.get_for_role(dashboard.id, role)
            if granted is not None and granted.enabled:
                best = self._stronger(best, permission_of(granted.permission))

        if best is None:
            return DENIED
        return Access(allowed=True, permission=best)

    async def require_access(
        self,
        dashboard: Dashboard,
        *,
        user_id: UUID | None,
        roles: list[str] | None = None,
        need: SharePermission = SharePermission.VIEW,
    ) -> Access:
        """Resolve access and refuse if it is insufficient.

        Raises:
            AuthorizationError: If the caller lacks *need*.
        """
        access = await self.resolve_access(dashboard, user_id=user_id, roles=roles)
        if not access.allowed or access.permission is None:
            raise AuthorizationError(DENIED.reason or "Access denied.")
        if _RANK[access.permission] < _RANK[need]:
            raise AuthorizationError(
                f"This action needs {str(need)!r} access; you have " f"{str(access.permission)!r}."
            )
        return access

    async def share_with_user(
        self,
        dashboard: Dashboard,
        *,
        user_id: UUID,
        permission: SharePermission = SharePermission.VIEW,
        shared_by: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> DashboardShare:
        """Share a dashboard directly with one person."""
        share = await self._shares.create(
            DashboardShare(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard.id,
                shared_with_user_id=user_id,
                permission=permission,
                expires_at=expires_at,
                shared_by=shared_by,
            )
        )
        await self._publish_event(
            DashboardSharedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "dashboard_id": str(dashboard.id),
                    "shared_with_user_id": str(user_id),
                    "permission": str(permission),
                },
            )
        )
        return share

    async def create_link(
        self,
        dashboard: Dashboard,
        *,
        shared_by: UUID | None = None,
        ttl_seconds: int | None = None,
    ) -> tuple[DashboardShare, str]:
        """Mint a read-only link.

        Returns the share and its token. The token is returned here and
        nowhere else -- :meth:`list_shares` deliberately omits it.

        A link always grants ``VIEW``: handing edit rights to whoever
        holds a URL is not a thing this service will do.
        """
        token = new_share_token()
        share = await self._shares.create(
            DashboardShare(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard.id,
                permission=SharePermission.VIEW,
                share_token=token,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds or self._link_ttl),
                shared_by=shared_by,
            )
        )
        await self._publish_event(
            DashboardSharedEvent(
                source_service=SOURCE_SERVICE,
                payload={"dashboard_id": str(dashboard.id), "channel": "link"},
            )
        )
        return share, token

    async def resolve_link(self, token: str) -> Dashboard:
        """Resolve a link token to its dashboard.

        Raises:
            NotFoundError: If the token is unknown.
            ConflictError: If the link is revoked or expired. Expiry is
                enforced here -- an ``expires_at`` nothing checks makes
                a link time-limited in name only.
        """
        share = await self._shares.get_by_token(token)
        if share is None:
            raise NotFoundError("That dashboard link is not valid.")
        if share.is_revoked:
            raise ConflictError("That dashboard link has been revoked.")
        if self._is_expired(share):
            raise ConflictError("That dashboard link has expired.")

        share.access_count += 1
        await self._shares.update(share)
        return await self._dashboards.require_by_id(share.dashboard_id)

    async def get_share(self, share_id: UUID) -> DashboardShare:
        """Return one share.

        Raises:
            NotFoundError: If no such share exists.
        """
        return await self._shares.require_by_id(share_id)

    async def revoke(self, share_id: UUID, *, revoked_by: UUID | None = None) -> DashboardShare:
        """Revoke a share.

        The row is kept and marked revoked rather than deleted:
        "who used to have access?" is a question an auditor asks, and a
        deleted row cannot answer it.

        Raises:
            NotFoundError: If no such share exists.
            ConflictError: If it is already revoked.
        """
        share = await self._shares.require_by_id(share_id)
        if share.is_revoked:
            raise ConflictError("That share is already revoked.")
        share.is_revoked = True
        share.revoked_at = datetime.now(UTC)
        if revoked_by is not None:
            share.updated_by = revoked_by
        return await self._shares.update(share)

    async def list_shares(
        self, dashboard_id: UUID, *, active_only: bool = False
    ) -> list[DashboardShare]:
        """Shares of one dashboard.

        Callers must not expose ``share_token`` from these rows; see
        this module's docstring.
        """
        return await self._shares.list_for_dashboard(dashboard_id, active_only=active_only)

    async def grant_role(
        self,
        dashboard: Dashboard,
        *,
        role: str,
        permission: SharePermission = SharePermission.VIEW,
        granted_by: UUID | None = None,
    ) -> DashboardPermission:
        """Grant or update a role's standing permission."""
        existing = await self._permissions.get_for_role(dashboard.id, role)
        if existing is not None:
            existing.permission = permission
            existing.enabled = True
            existing.granted_by = granted_by
            return await self._permissions.update(existing)
        return await self._permissions.create(
            DashboardPermission(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard.id,
                role=role,
                permission=permission,
                granted_by=granted_by,
            )
        )

    async def revoke_role(self, dashboard_id: UUID, role: str) -> bool:
        """Withdraw a role's permission; returns whether anything changed."""
        existing = await self._permissions.get_for_role(dashboard_id, role)
        if existing is None or not existing.enabled:
            return False
        existing.enabled = False
        await self._permissions.update(existing)
        return True

    async def list_role_permissions(self, dashboard_id: UUID) -> list[DashboardPermission]:
        """Standing role permissions on one dashboard."""
        return await self._permissions.list_for_dashboard(dashboard_id)

    @staticmethod
    def _is_expired(share: DashboardShare) -> bool:
        """Whether a share has passed its expiry."""
        return share.expires_at is not None and share.expires_at <= datetime.now(UTC)

    @staticmethod
    def _stronger(current: SharePermission | None, candidate: SharePermission) -> SharePermission:
        """The more permissive of two grants."""
        if current is None:
            return candidate
        return candidate if _RANK[candidate] > _RANK[current] else current


__all__ = ["DENIED", "Access", "SharingService", "new_share_token", "permission_of"]
