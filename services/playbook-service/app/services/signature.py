"""Playbook digital signatures. Per docs/041 "SECURITY" "Support":
Digital Signatures, Checksum Validation, Publisher Verification,
Content Integrity, Signature Verification.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.playbook_events import SignatureVerifiedEvent
from app.models.enums import SignatureAlgorithm
from app.models.playbook_signature import PlaybookSignature
from app.repositories.playbook_signature import PlaybookSignatureRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.signing.signer import compute_fingerprint, sign_checksum, verify_signature

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class PlaybookSignatureService:
    """Signs and verifies playbook version content, and reads signature history."""

    def __init__(
        self,
        signatures: PlaybookSignatureRepository,
        versions: PlaybookVersionRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._signatures = signatures
        self._versions = versions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_version(self, version_id: UUID) -> list[PlaybookSignature]:
        """Every signature recorded for *version_id*."""
        return await self._signatures.list_for_version(version_id)

    async def sign(
        self,
        version_id: UUID,
        *,
        signer_id: UUID | None,
        private_key_pem: str,
        public_key_pem: str,
    ) -> PlaybookSignature:
        """Sign a version's own content checksum with an Ed25519 private key.

        Raises:
            NotFoundError: If *version_id* does not exist.
            SigningError: If the given key material is malformed or
                the wrong algorithm.
        """
        version = await self._versions.require_by_id(version_id)
        signature_value = sign_checksum(version.checksum, private_key_pem=private_key_pem)
        fingerprint = compute_fingerprint(public_key_pem)
        # A signature this service just produced with its own key is,
        # by construction, immediately verified -- no separate
        # verify() round trip is needed before recording that fact.
        verified = verify_signature(
            version.checksum, signature=signature_value, public_key_pem=public_key_pem
        )
        signature = await self._signatures.create(
            PlaybookSignature(
                organization_id=version.organization_id,
                playbook_id=version.playbook_id,
                version_id=version_id,
                signer_id=signer_id,
                algorithm=SignatureAlgorithm.ED25519,
                public_key_fingerprint=fingerprint,
                signature=signature_value,
                checksum=version.checksum,
                verified=verified,
                signed_at=datetime.now(UTC),
            )
        )
        if verified:
            await self._publish(
                SignatureVerifiedEvent(
                    source_service="playbook-service",
                    payload={"signature_id": str(signature.id), "version_id": str(version_id)},
                )
            )
        return signature

    async def verify(self, signature_id: UUID, *, public_key_pem: str) -> bool:
        """Independently re-verify a recorded signature against
        *public_key_pem* ("Publisher Verification") and record the
        outcome.

        Raises:
            NotFoundError: If *signature_id* does not exist.
        """
        signature = await self._signatures.require_by_id(signature_id)
        is_valid = verify_signature(
            signature.checksum, signature=signature.signature, public_key_pem=public_key_pem
        )
        signature.verified = is_valid
        await self._signatures.update(signature)
        if is_valid:
            await self._publish(
                SignatureVerifiedEvent(
                    source_service="playbook-service",
                    payload={
                        "signature_id": str(signature_id),
                        "version_id": str(signature.version_id),
                    },
                )
            )
        return is_valid


__all__ = ["PlaybookSignatureService"]
