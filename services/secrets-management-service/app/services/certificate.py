"""Certificate store ("CERTIFICATE MANAGEMENT": TLS/Client/CA
Certificates, Certificate Chains, Import, Expiration Tracking,
Revocation).

The certificate's private key, when supplied, is stored as a
:class:`~app.models.secret.Secret` (via
:class:`~app.services.secret.SecretService`, so it gets the same
envelope encryption, versioning, and audit trail as every other
secret) and referenced by :attr:`~app.models.certificate.Certificate.private_key_secret_id`
-- see ``app/models/certificate.py``'s own docstring for why the
certificate itself stays plaintext.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.certificates.importer import parse_certificate_pem
from app.events.secret_events import CertificateImportedEvent
from app.models.certificate import Certificate
from app.models.enums import CertificateType, SecretType
from app.repositories.certificate import CertificateRepository
from app.services.secret import SecretService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class CertificateService:
    """Imports, lists, and deletes certificates."""

    def __init__(
        self,
        certificates: CertificateRepository,
        secrets: SecretService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._certificates = certificates
        self._secrets = secrets
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_org(self, organization_id: UUID) -> list[Certificate]:
        """Every certificate belonging to *organization_id*."""
        return await self._certificates.list_for_org(organization_id)

    async def import_certificate(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        certificate_type: CertificateType,
        certificate_pem: str,
        chain_pem: list[str],
        private_key: str | None,
        owner_id: UUID | None,
    ) -> Certificate:
        """Import a certificate, optionally with its private key ("Import").

        Raises:
            ValueError: If *certificate_pem* is malformed, or *private_key*
                is given without *owner_id*.
            ConflictError: If a certificate with the same fingerprint is
                already imported.
        """
        parsed = parse_certificate_pem(certificate_pem)
        if await self._certificates.get_by_fingerprint(parsed.fingerprint) is not None:
            raise ConflictError(
                f"Certificate with fingerprint {parsed.fingerprint!r} already exists."
            )

        private_key_secret_id: UUID | None = None
        if private_key is not None:
            if owner_id is None:
                raise ValueError("owner_id is required when importing a certificate's private key.")
            secret = await self._secrets.create(
                organization_id=organization_id,
                project_id=project_id,
                name=f"{name} (private key)",
                description=f"Private key for certificate {name!r}.",
                category_id=None,
                secret_type=SecretType.PRIVATE_KEY,
                owner_id=owner_id,
                value=private_key,
                expires_at=None,
                rotation_policy={},
                metadata={},
                tags=[],
            )
            private_key_secret_id = secret.id

        certificate = await self._certificates.create(
            Certificate(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                certificate_type=certificate_type,
                certificate_pem=certificate_pem,
                chain_pem=chain_pem,
                private_key_secret_id=private_key_secret_id,
                subject=parsed.subject,
                issuer=parsed.issuer,
                serial_number=parsed.serial_number,
                fingerprint=parsed.fingerprint,
                not_before=parsed.not_before,
                not_after=parsed.not_after,
                status=parsed.status,
            )
        )
        await self._publish(
            CertificateImportedEvent(
                source_service="secrets-management-service",
                payload={"certificate_id": str(certificate.id)},
            )
        )
        return certificate

    async def delete(self, certificate_id: UUID) -> None:
        """Delete a certificate ("Revocation").

        Raises:
            NotFoundError: If no such certificate exists.
        """
        await self._certificates.delete(certificate_id)

    async def list_expiring_before(self, cutoff: datetime) -> list[Certificate]:
        """Every non-expired, non-revoked certificate expiring before
        *cutoff* ("Expiration Tracking").
        """
        return await self._certificates.list_expiring_before(cutoff)


__all__ = ["CertificateService"]
