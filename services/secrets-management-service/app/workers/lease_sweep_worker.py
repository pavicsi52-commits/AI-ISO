"""Background lease sweeping. Per docs/035 "SECRET LEASING": Lease
Expiration; "NOTIFICATIONS": Lease Expired.
"""

from __future__ import annotations

from app.notifications.secret_notifications import SecretNotificationService
from app.services.lease import SecretLeaseService
from app.services.secret import SecretService


async def sweep_expired_leases(
    leases: SecretLeaseService, secrets: SecretService, notifications: SecretNotificationService
) -> None:
    """Mark past-due, still-``ACTIVE`` leases ``EXPIRED`` ("Lease
    Expiration") and notify each lease's principal ("Lease Expired").
    """
    for lease in await leases.sweep_expired():
        secret = await secrets.get_by_id(lease.secret_id)
        await notifications.send_lease_expired(str(lease.principal_id), secret_name=secret.name)


__all__ = ["sweep_expired_leases"]
