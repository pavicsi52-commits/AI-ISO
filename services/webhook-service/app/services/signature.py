"""Signing-secret management (docs/057 "SIGNATURE MANAGEMENT").

Secrets are encrypted at rest via `shared_core.security.encryption`
(AES-256-GCM) -- unlike API keys elsewhere in this platform, a webhook
signing secret must be recovered in *plaintext* to compute an HMAC over
each outgoing payload, so hashing (irreversible) is the wrong primitive
here; encryption (reversible, given the master key) is the right one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.security.encryption import decrypt, encrypt

from app.models.enums import SecretStatus, SignatureAlgorithm
from app.models.signature import WebhookSignature
from app.repositories.signature import WebhookSignatureRepository
from app.signatures.engine import SigningSecret


class SignatureService:
    """An endpoint's own signing secrets: creation, rotation, and decrypted lookup."""

    def __init__(self, signatures: WebhookSignatureRepository, *, encryption_key: str) -> None:
        self._signatures = signatures
        self._encryption_key = encryption_key

    async def create(
        self,
        organization_id: UUID,
        *,
        endpoint_id: UUID,
        secret: str,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    ) -> WebhookSignature:
        """Register the first signing secret for an endpoint."""
        next_version = await self._signatures.get_latest_version(endpoint_id) + 1
        return await self._signatures.create(
            WebhookSignature(
                organization_id=organization_id,
                endpoint_id=endpoint_id,
                version=next_version,
                algorithm=algorithm,
                secret_ciphertext=encrypt(secret, key=self._encryption_key),
            )
        )

    async def rotate(
        self,
        organization_id: UUID,
        *,
        endpoint_id: UUID,
        new_secret: str,
        overlap_hours: int = 24,
    ) -> WebhookSignature:
        """Rotate an endpoint's own signing secret.

        The previous ``ACTIVE`` secret (if any) moves to ``ROTATING`` and
        is given an expiry *overlap_hours* from now -- so a partner that
        cached the old secret still verifies successfully until the
        overlap ends, rather than every in-flight integration breaking
        the instant a secret rotates.
        """
        current = await self._signatures.get_active_for_endpoint(endpoint_id)
        now = datetime.now(UTC)
        if current is not None:
            current.status = SecretStatus.ROTATING
            current.rotated_at = now
            current.expires_at = now + timedelta(hours=overlap_hours)
            await self._signatures.update(current)

        next_version = await self._signatures.get_latest_version(endpoint_id) + 1
        return await self._signatures.create(
            WebhookSignature(
                organization_id=organization_id,
                endpoint_id=endpoint_id,
                version=next_version,
                algorithm=current.algorithm if current else SignatureAlgorithm.HMAC_SHA256,
                secret_ciphertext=encrypt(new_secret, key=self._encryption_key),
            )
        )

    async def usable_secrets_for(self, endpoint_id: UUID) -> list[SigningSecret]:
        """Every ``ACTIVE``/``ROTATING`` secret for an endpoint, decrypted, newest first."""
        rows = await self._signatures.list_usable_for_endpoint(endpoint_id)
        return [
            SigningSecret(
                version=row.version,
                secret=decrypt(row.secret_ciphertext, key=self._encryption_key),
                algorithm=SignatureAlgorithm(row.algorithm),
            )
            for row in rows
        ]

    async def active_secret_for(self, endpoint_id: UUID) -> SigningSecret | None:
        """The one ``ACTIVE`` secret for an endpoint, decrypted -- used to sign new deliveries."""
        row = await self._signatures.get_active_for_endpoint(endpoint_id)
        if row is None:
            return None
        return SigningSecret(
            version=row.version,
            secret=decrypt(row.secret_ciphertext, key=self._encryption_key),
            algorithm=SignatureAlgorithm(row.algorithm),
        )

    async def expire_due(self, *, now: datetime, limit: int = 500) -> int:
        """Move every ``ROTATING`` secret whose overlap has ended to ``EXPIRED``.

        Returns how many were expired.
        """
        rows = await self._signatures.list_rotating_due_for_expiry(now=now, limit=limit)
        for row in rows:
            row.status = SecretStatus.EXPIRED
            await self._signatures.update(row)
        return len(rows)


__all__ = ["SignatureService"]
