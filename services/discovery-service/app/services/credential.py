"""Discovery credential *reference* management -- never the secret
material itself. See ``app/models/discovery_credential.py``'s own
docstring for why only :attr:`~app.models.discovery_credential
.DiscoveryCredential.secret_id` is ever stored.
"""

from __future__ import annotations

from uuid import UUID

from app.models.discovery_credential import DiscoveryCredential
from app.models.enums import CredentialType, ProtocolType
from app.repositories.discovery_credential import DiscoveryCredentialRepository
from app.schemas.scan import InlineCredentialSpec


class DiscoveryCredentialService:
    """Creates (from an inline spec) and looks up credential references."""

    def __init__(self, credentials: DiscoveryCredentialRepository) -> None:
        self._credentials = credentials

    async def get_by_id(self, credential_id: UUID) -> DiscoveryCredential:
        """Return the credential reference identified by *credential_id*.

        Raises:
            NotFoundError: If no such credential reference exists.
        """
        return await self._credentials.require_by_id(credential_id)

    async def create_from_spec(
        self, spec: InlineCredentialSpec, *, organization_id: UUID, protocol: ProtocolType
    ) -> DiscoveryCredential:
        """Create the :class:`DiscoveryCredential` row an inline
        ``/discovery/*-scan`` request's credential spec names -- see
        ``app/schemas/scan.py``'s own module docstring for why scan
        requests carry this instead of a pre-registered credential id.
        """
        existing = await self._credentials.get_by_name(organization_id, spec.name)
        if existing is not None:
            return existing
        return await self._credentials.create(
            DiscoveryCredential(
                organization_id=organization_id,
                name=spec.name,
                protocol=protocol,
                credential_type=CredentialType(spec.credential_type),
                secret_id=spec.secret_id,
                username=spec.username,
            )
        )


__all__ = ["DiscoveryCredentialService"]
