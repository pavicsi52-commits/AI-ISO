"""Secret providers ("SECRET PROVIDERS": Provider Abstraction Layer).

Registers external (or the internal) provider configurations. Per
``app/models/secret_provider.py``'s own docstring, a provider's own
connection credential (an IAM role, a Vault token) is stored as a
:class:`~app.models.secret.Secret` and referenced by
:attr:`~app.models.secret_provider.SecretProvider.connection_secret_id`
rather than embedded here -- creating that secret, if needed, is the
caller's responsibility (via
:class:`~app.services.secret.SecretService`) before registering the
provider. Actually calling out to an external provider's own API
(fetching/pushing secrets from HashiCorp Vault, AWS Secrets Manager,
etc.) is explicitly out of scope here -- docs/035's own "DO NOT
IMPLEMENT" excludes "Connector Execution", and no such client library
integration is named anywhere in "SECRET PROVIDERS"; only the
abstraction layer's *configuration* is implemented.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import ProviderType
from app.models.secret_provider import SecretProvider
from app.repositories.secret_provider import SecretProviderRepository


class SecretProviderService:
    """Registers and lists external (or internal) secret provider configurations."""

    def __init__(self, providers: SecretProviderRepository) -> None:
        self._providers = providers

    async def list_for_org(self, organization_id: UUID) -> list[SecretProvider]:
        """Every provider configured for *organization_id*."""
        return await self._providers.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        provider_type: ProviderType,
        config: dict[str, Any],
        connection_secret_id: UUID | None,
        is_enabled: bool,
    ) -> SecretProvider:
        """Register a new provider configuration.

        Raises:
            ConflictError: If *name* is already taken within *organization_id*.
        """
        if await self._providers.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Provider {name!r} already exists in this organization.")
        return await self._providers.create(
            SecretProvider(
                organization_id=organization_id,
                name=name,
                provider_type=provider_type,
                config=config,
                connection_secret_id=connection_secret_id,
                is_enabled=is_enabled,
            )
        )


__all__ = ["SecretProviderService"]
