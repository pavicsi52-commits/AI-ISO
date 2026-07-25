"""API key store ("API KEY MANAGEMENT": Generation, Scopes, Expiration,
Usage Tracking).

Stores third-party/outbound API keys -- the value is always stored as
a :class:`~app.models.secret.Secret` (via
:class:`~app.services.secret.SecretService`), referenced by
:attr:`~app.models.api_key.ApiKeyEntry.secret_id` -- see
``app/models/api_key.py``'s own docstring for the distinction from
``shared_core.security.apikey``'s inbound, hash-only keys. That module's
:func:`~shared_core.security.apikey.generate_api_key` is reused here
purely as a convenient random-value generator when the caller doesn't
supply their own key value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.security.apikey import generate_api_key

from app.models.api_key import ApiKeyEntry
from app.models.enums import ApiKeyStatus, SecretType
from app.repositories.api_key import ApiKeyRepository
from app.services.secret import SecretService

_KEY_PREFIX_LENGTH = 12


class ApiKeyService:
    """Generates or imports, lists, and deletes managed API keys."""

    def __init__(self, api_keys: ApiKeyRepository, secrets: SecretService) -> None:
        self._api_keys = api_keys
        self._secrets = secrets

    async def list_for_org(self, organization_id: UUID) -> list[ApiKeyEntry]:
        """Every managed API key belonging to *organization_id*."""
        return await self._api_keys.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        owner_id: UUID,
        scopes: list[str],
        expires_at: datetime | None,
        value: str | None,
    ) -> tuple[ApiKeyEntry, str]:
        """Generate a fresh key value (when *value* is ``None``) or import
        an existing one ("Generation").

        Returns:
            ``(api_key, value)`` -- the key value is returned once here,
            at creation time, and never again.
        """
        if value is None:
            value = generate_api_key()

        secret = await self._secrets.create(
            organization_id=organization_id,
            project_id=project_id,
            name=f"{name} (key value)",
            description=f"Value for API key {name!r}.",
            category_id=None,
            secret_type=SecretType.API_KEY,
            owner_id=owner_id,
            value=value,
            expires_at=expires_at,
            rotation_policy={},
            metadata={},
            tags=[],
        )
        api_key = await self._api_keys.create(
            ApiKeyEntry(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                key_prefix=value[:_KEY_PREFIX_LENGTH],
                secret_id=secret.id,
                scopes=scopes,
                status=ApiKeyStatus.ACTIVE,
                expires_at=expires_at,
            )
        )
        return api_key, value

    async def mark_used(self, api_key_id: UUID) -> ApiKeyEntry:
        """Record that a key was just used ("Usage Tracking").

        Raises:
            NotFoundError: If no such API key exists.
        """
        api_key = await self._api_keys.require_by_id(api_key_id)
        api_key.last_used_at = datetime.now(UTC)
        return api_key

    async def delete(self, api_key_id: UUID) -> None:
        """Delete an API key ("Revocation").

        Raises:
            NotFoundError: If no such API key exists.
        """
        await self._api_keys.delete(api_key_id)


__all__ = ["ApiKeyService"]
