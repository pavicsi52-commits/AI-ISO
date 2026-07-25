"""Secret leasing ("SECRET LEASING": Temporary Credentials, Lease
Duration, Renew Lease, Revoke Lease, Lease Expiration, Lease Audit).

A lease grants temporary access to a secret's *current* decrypted
value -- the value is resolved once, at issue (or renewal) time, via
:class:`~app.services.secret_version.SecretVersionService`, never
cached alongside the lease row itself (docs/035's own "PERFORMANCE":
"Never cache decrypted secrets").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.secret_events import LeaseCreatedEvent, LeaseExpiredEvent
from app.leasing.policy import compute_expiry, is_lease_expired
from app.models.enums import LeaseStatus
from app.models.secret_lease import SecretLease
from app.repositories.secret_lease import SecretLeaseRepository
from app.services.secret_version import SecretVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class SecretLeaseService:
    """Issues, renews, revokes, and sweeps temporary-credential leases."""

    def __init__(
        self,
        leases: SecretLeaseRepository,
        versions: SecretVersionService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._leases = leases
        self._versions = versions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, lease_id: UUID) -> SecretLease:
        """Return the lease identified by *lease_id*.

        Raises:
            NotFoundError: If no such lease exists.
        """
        return await self._leases.require_by_id(lease_id)

    async def issue(
        self, secret_id: UUID, *, organization_id: UUID, principal_id: UUID, duration_seconds: int
    ) -> tuple[SecretLease, str]:
        """Issue a new lease on *secret_id*'s current value ("Temporary
        Credentials").

        Returns:
            ``(lease, decrypted_value)``.

        Raises:
            NotFoundError: If *secret_id* has no current version.
        """
        current = await self._versions.get_current(secret_id)
        plaintext = await self._versions.decrypt(current)
        issued_at = datetime.now(UTC)
        lease = await self._leases.create(
            SecretLease(
                secret_id=secret_id,
                organization_id=organization_id,
                principal_id=principal_id,
                status=LeaseStatus.ACTIVE,
                issued_at=issued_at,
                expires_at=compute_expiry(issued_at=issued_at, duration_seconds=duration_seconds),
                lease_duration_seconds=duration_seconds,
                renewed_count=0,
            )
        )
        await self._publish(
            LeaseCreatedEvent(
                source_service="secrets-management-service",
                payload={"lease_id": str(lease.id), "secret_id": str(secret_id)},
            )
        )
        return lease, plaintext

    async def revoke(self, lease_id: UUID) -> SecretLease:
        """Revoke a lease ("Revoke Lease").

        Raises:
            NotFoundError: If no such lease exists.
        """
        lease = await self.get_by_id(lease_id)
        lease.status = LeaseStatus.REVOKED
        return lease

    async def sweep_expired(self, *, now: datetime | None = None) -> list[SecretLease]:
        """Mark every past-due, still-``ACTIVE`` lease ``EXPIRED`` ("Lease
        Expiration"), publishing a
        :class:`~app.events.secret_events.LeaseExpiredEvent` for each.
        """
        current = now or datetime.now(UTC)
        due = await self._leases.list_active_expired_before(current)
        for lease in due:
            if is_lease_expired(expires_at=lease.expires_at, now=current):
                lease.status = LeaseStatus.EXPIRED
                await self._publish(
                    LeaseExpiredEvent(
                        source_service="secrets-management-service",
                        payload={"lease_id": str(lease.id), "secret_id": str(lease.secret_id)},
                    )
                )
        return due


__all__ = ["SecretLeaseService"]
