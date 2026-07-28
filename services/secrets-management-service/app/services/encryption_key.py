"""Data Encryption Key lifecycle ("KEY MANAGEMENT": Data Keys, Key
Rotation, Key Versioning, Key Revocation; "ENCRYPTION": Envelope
Encryption, Automatic Key Rotation).

One organization always has exactly one *active* DEK at a time (see
``app/repositories/encryption_key.py``'s docstring for why DEKs are
per-organization); rotating mints a new one and retires the old, but
leaves already-encrypted secret values under the old key until
explicitly migrated -- :meth:`EncryptionKeyService.rotate` only rotates
the *key*. Re-encrypting affected secret values under the new key is
:meth:`app.services.secret_version.SecretVersionService.migrate_key`'s
job, since that requires walking every
:class:`~app.models.secret_version.SecretVersion` row, a concern this
service deliberately doesn't own.

Publishes :class:`~app.events.secret_events.KeyGeneratedEvent` and
:class:`~app.events.secret_events.KeyRevokedEvent` -- docs/035's
"EVENTS" list names these once, generically, and this is the "KEY
MANAGEMENT" section's own vocabulary ("Master Keys, Data Keys, Key
Rotation, Key Versioning, Key Revocation"), so they're scoped here to
DEK lifecycle rather than SSH/API key generation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.encryption.envelope import EnvelopeEncryption
from app.events.secret_events import KeyGeneratedEvent, KeyRevokedEvent
from app.models.encryption_key import EncryptionKey
from app.models.enums import EncryptionKeyStatus
from app.repositories.encryption_key import EncryptionKeyRepository
from app.services.key_rotation_history import KeyRotationHistoryService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class EncryptionKeyService:
    """Mints, retrieves, and rotates an organization's Data Encryption Keys."""

    def __init__(
        self,
        keys: EncryptionKeyRepository,
        envelope: EnvelopeEncryption,
        history: KeyRotationHistoryService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._keys = keys
        self._envelope = envelope
        self._history = history
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, key_id: UUID) -> EncryptionKey:
        """Return the DEK identified by *key_id*.

        Raises:
            NotFoundError: If no such key exists.
        """
        return await self._keys.require_by_id(key_id)

    async def get_or_create_active(self, organization_id: UUID) -> EncryptionKey:
        """Return *organization_id*'s current active DEK, minting the very
        first one if none exists yet ("Data Keys").
        """
        active = await self._keys.get_active(organization_id)
        if active is not None:
            return active
        return await self._mint(organization_id, version=1)

    async def _mint(self, organization_id: UUID, *, version: int) -> EncryptionKey:
        raw_dek = self._envelope.generate_dek()
        wrapped = self._envelope.wrap_dek(raw_dek)
        key = await self._keys.create(
            EncryptionKey(
                organization_id=organization_id,
                key_version=version,
                wrapped_key=wrapped,
                status=EncryptionKeyStatus.ACTIVE,
            )
        )
        await self._publish(
            KeyGeneratedEvent(
                source_service="secrets-management-service",
                payload={"encryption_key_id": str(key.id), "organization_id": str(organization_id)},
            )
        )
        return key

    async def revoke(self, key_id: UUID) -> EncryptionKey:
        """Revoke a DEK outright ("Key Revocation") -- distinct from
        :meth:`rotate`, which merely retires a key by superseding it with
        a new active one. A revoked key can no longer be used to decrypt
        (callers are responsible for having migrated any secrets still
        under it first).

        Raises:
            NotFoundError: If no such key exists.
        """
        key = await self._keys.require_by_id(key_id)
        key.status = EncryptionKeyStatus.REVOKED
        await self._publish(
            KeyRevokedEvent(
                source_service="secrets-management-service",
                payload={"encryption_key_id": str(key.id)},
            )
        )
        return key

    async def rotate(
        self,
        organization_id: UUID,
        *,
        rotated_by: UUID | None,
        reason: str | None = None,
        secrets_migrated_count: int = 0,
    ) -> tuple[EncryptionKey | None, EncryptionKey]:
        """Mint a new active DEK for *organization_id*, retiring the
        previous one ("Key Rotation").

        Returns:
            ``(previous_key, new_key)`` -- *previous_key* is ``None`` if
            this organization had no active DEK yet (its very first
            "rotation" is really just the initial mint).
        """
        previous = await self._keys.get_active(organization_id)
        next_version = (previous.key_version + 1) if previous is not None else 1
        new_key = await self._mint(organization_id, version=next_version)
        if previous is not None:
            previous.status = EncryptionKeyStatus.ROTATED
        await self._history.record(
            organization_id=organization_id,
            encryption_key_id=new_key.id,
            previous_key_id=previous.id if previous is not None else None,
            rotated_by=rotated_by,
            reason=reason,
            secrets_migrated_count=secrets_migrated_count,
        )
        return previous, new_key

    async def encrypt(self, organization_id: UUID, plaintext: str) -> tuple[str, EncryptionKey]:
        """Encrypt *plaintext* under *organization_id*'s active DEK ("Encryption").

        Returns:
            ``(ciphertext, key)`` -- the encrypted value and the DEK it
            was encrypted under, so the caller can persist
            :attr:`~app.models.secret_version.SecretVersion.encryption_key_id`.
        """
        key = await self.get_or_create_active(organization_id)
        ciphertext = self._envelope.encrypt_value(plaintext, wrapped_dek=key.wrapped_key)
        return ciphertext, key

    def decrypt(self, ciphertext: str, key: EncryptionKey) -> str:
        """Decrypt *ciphertext* that was encrypted under *key* ("Decryption")."""
        return self._envelope.decrypt_value(ciphertext, wrapped_dek=key.wrapped_key)

    def reencrypt(self, ciphertext: str, *, old_key: EncryptionKey, new_key: EncryptionKey) -> str:
        """Re-encrypt *ciphertext* from *old_key* to *new_key*, without
        changing the underlying plaintext ("Automatic Key Rotation").
        """
        return self._envelope.reencrypt_value(
            ciphertext, old_wrapped_dek=old_key.wrapped_key, new_wrapped_dek=new_key.wrapped_key
        )


__all__ = ["EncryptionKeyService"]
