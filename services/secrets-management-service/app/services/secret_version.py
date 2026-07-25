"""Secret value versioning ("SECRET VERSIONING": Multiple Versions,
Rollback, Version History, Current Version, Previous Versions, Version
Comparison).

Every write of a secret's *value* (initial creation, rotation, or
rollback) creates a brand-new immutable
:class:`~app.models.secret_version.SecretVersion` row rather than
mutating an existing one -- "rollback" therefore means creating a new,
current version whose plaintext matches an older one, never rewinding
history in place.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.encryption_key import EncryptionKey
from app.models.secret_version import SecretVersion
from app.repositories.secret_version import SecretVersionRepository
from app.services.encryption_key import EncryptionKeyService


class SecretVersionService:
    """Creates, reads, and decrypts a secret's value versions."""

    def __init__(self, versions: SecretVersionRepository, keys: EncryptionKeyService) -> None:
        self._versions = versions
        self._keys = keys

    async def get_current(self, secret_id: UUID) -> SecretVersion:
        """Return *secret_id*'s current version.

        Raises:
            NotFoundError: If *secret_id* has no version yet.
        """
        version = await self._versions.get_current(secret_id)
        if version is None:
            raise NotFoundError(f"Secret '{secret_id}' has no current version.")
        return version

    async def get_by_number(self, secret_id: UUID, version_number: int) -> SecretVersion:
        """Return *secret_id*'s version identified by *version_number*.

        Raises:
            NotFoundError: If no such version exists.
        """
        version = await self._versions.get_by_number(secret_id, version_number)
        if version is None:
            raise NotFoundError(f"Secret '{secret_id}' has no version numbered {version_number}.")
        return version

    async def list_for_secret(self, secret_id: UUID) -> list[SecretVersion]:
        """Every version of *secret_id*, newest first ("Version History")."""
        return await self._versions.list_for_secret(secret_id)

    async def decrypt(self, version: SecretVersion) -> str:
        """Decrypt *version*'s plaintext value ("Decryption")."""
        key = await self._keys.get_by_id(version.encryption_key_id)
        return self._keys.decrypt(version.ciphertext, key)

    async def create_version(
        self,
        secret_id: UUID,
        *,
        organization_id: UUID,
        plaintext: str,
        created_by: UUID | None,
    ) -> SecretVersion:
        """Encrypt *plaintext* and store it as *secret_id*'s new current
        version, demoting whatever was previously current.
        """
        previous = await self._versions.get_current(secret_id)
        if previous is not None:
            previous.is_current = False
        next_number = (previous.version_number + 1) if previous is not None else 1
        ciphertext, key = await self._keys.encrypt(organization_id, plaintext)
        return await self._versions.create(
            SecretVersion(
                secret_id=secret_id,
                organization_id=organization_id,
                version_number=next_number,
                encryption_key_id=key.id,
                ciphertext=ciphertext,
                is_current=True,
                created_by=created_by,
            )
        )

    async def rollback(
        self,
        secret_id: UUID,
        *,
        organization_id: UUID,
        target_version_number: int,
        rolled_back_by: UUID | None,
    ) -> SecretVersion:
        """Roll *secret_id* back to the plaintext held by
        *target_version_number*, by creating a new current version with
        that plaintext ("Rollback").

        Raises:
            NotFoundError: If *target_version_number* doesn't exist.
        """
        target = await self.get_by_number(secret_id, target_version_number)
        plaintext = await self.decrypt(target)
        return await self.create_version(
            secret_id,
            organization_id=organization_id,
            plaintext=plaintext,
            created_by=rolled_back_by,
        )

    async def migrate_key(self, *, old_key: EncryptionKey, new_key: EncryptionKey) -> int:
        """Re-encrypt every version still under *old_key* to *new_key*,
        without creating new version rows or changing any plaintext
        ("Automatic Key Rotation"). Returns the number of versions migrated.
        """
        versions = await self._versions.list_by_encryption_key(old_key.id)
        for version in versions:
            version.ciphertext = self._keys.reencrypt(
                version.ciphertext, old_key=old_key, new_key=new_key
            )
            version.encryption_key_id = new_key.id
        return len(versions)


__all__ = ["SecretVersionService"]
