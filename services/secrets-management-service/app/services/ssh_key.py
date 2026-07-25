"""SSH key store ("SSH KEY MANAGEMENT": RSA, ECDSA, Ed25519, Key
Generation, Import, Export, Fingerprint Validation, Expiration).

The private key is always stored as a
:class:`~app.models.secret.Secret` (via
:class:`~app.services.secret.SecretService`), referenced by
:attr:`~app.models.ssh_key.SSHKey.private_key_secret_id` -- see
``app/models/ssh_key.py``'s own docstring for why the public key stays
plaintext.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import SecretType, SSHKeyStatus, SSHKeyType
from app.models.ssh_key import SSHKey
from app.repositories.ssh_key import SSHKeyRepository
from app.services.secret import SecretService
from app.ssh.keygen import compute_fingerprint, generate_ssh_keypair


class SSHKeyService:
    """Generates or imports, lists, and deletes SSH keys."""

    def __init__(self, ssh_keys: SSHKeyRepository, secrets: SecretService) -> None:
        self._ssh_keys = ssh_keys
        self._secrets = secrets

    async def list_for_org(self, organization_id: UUID) -> list[SSHKey]:
        """Every SSH key belonging to *organization_id*."""
        return await self._ssh_keys.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        key_type: SSHKeyType,
        owner_id: UUID,
        expires_at: datetime | None,
        public_key: str | None,
        private_key: str | None,
    ) -> tuple[SSHKey, str]:
        """Generate a fresh keypair (when *public_key*/*private_key* are
        both ``None``) or import an existing one ("Key Generation"/
        "Import").

        Returns:
            ``(ssh_key, private_key_pem)`` -- the private key is returned
            once here, at creation time, and never again.

        Raises:
            ConflictError: If a key with the same fingerprint is already stored.
        """
        if public_key is None or private_key is None:
            private_key, public_key = generate_ssh_keypair(key_type)
        fingerprint = compute_fingerprint(public_key)
        if await self._ssh_keys.get_by_fingerprint(fingerprint) is not None:
            raise ConflictError(f"SSH key with fingerprint {fingerprint!r} already exists.")

        secret = await self._secrets.create(
            organization_id=organization_id,
            project_id=project_id,
            name=f"{name} (private key)",
            description=f"Private key for SSH key {name!r}.",
            category_id=None,
            secret_type=SecretType.SSH_KEY,
            owner_id=owner_id,
            value=private_key,
            expires_at=expires_at,
            rotation_policy={},
            metadata={},
            tags=[],
        )
        ssh_key = await self._ssh_keys.create(
            SSHKey(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                key_type=key_type,
                public_key=public_key,
                private_key_secret_id=secret.id,
                fingerprint=fingerprint,
                status=SSHKeyStatus.ACTIVE,
                expires_at=expires_at,
            )
        )
        return ssh_key, private_key

    async def delete(self, ssh_key_id: UUID) -> None:
        """Delete an SSH key.

        Raises:
            NotFoundError: If no such SSH key exists.
        """
        await self._ssh_keys.delete(ssh_key_id)


__all__ = ["SSHKeyService"]
