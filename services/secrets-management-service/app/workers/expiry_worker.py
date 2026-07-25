"""Background expiry checks. Per docs/035 "NOTIFICATIONS": Secret
Expiring, Certificate Expiring; "SECRET STATUS": Expired.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.notifications.secret_notifications import SecretNotificationService
from app.services.certificate import CertificateService
from app.services.secret import SecretService

_EXPIRY_WARNING_WINDOW = timedelta(days=7)


async def check_secret_expirations(
    secrets: SecretService, notifications: SecretNotificationService
) -> None:
    """Mark past-due secrets ``EXPIRED`` ("SecretExpired"), and warn
    owners of secrets expiring within the warning window ("Secret
    Expiring").
    """
    now = datetime.now(UTC)
    for secret in await secrets.list_expiring_before(now + _EXPIRY_WARNING_WINDOW):
        if await secrets.is_expired(secret, now=now):
            await secrets.mark_expired(secret.id)
        elif secret.expires_at is not None:
            days_left = (secret.expires_at - now).days
            await notifications.send_secret_expiring(
                str(secret.owner_id), secret_name=secret.name, days_left=days_left
            )


async def check_certificate_expirations(
    certificates: CertificateService,
    secrets: SecretService,
    notifications: SecretNotificationService,
) -> None:
    """Warn of certificates expiring within the warning window
    ("Certificate Expiring"). Only certificates with an associated
    private-key :class:`~app.models.secret.Secret` have a resolvable
    owner to notify -- a pure public-certificate import has nobody to
    notify and is silently skipped.
    """
    now = datetime.now(UTC)
    for certificate in await certificates.list_expiring_before(now + _EXPIRY_WARNING_WINDOW):
        if certificate.private_key_secret_id is None:
            continue
        owner = await secrets.get_by_id(certificate.private_key_secret_id)
        days_left = (certificate.not_after - now).days
        await notifications.send_certificate_expiring(
            str(owner.owner_id), certificate_name=certificate.name, days_left=days_left
        )


__all__ = ["check_certificate_expirations", "check_secret_expirations"]
