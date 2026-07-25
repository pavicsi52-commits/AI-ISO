"""API key lifecycle.

Per docs/030 "API KEYS": Personal API Keys, Organization API Keys,
Expiration, Rotation, Scopes, Revocation, Usage Tracking. Reuses
:func:`shared_core.security.apikey.create_api_key` for raw-key
generation and hashing, persisting the result into this service's own
:class:`app.models.apikey.ApiKey` row rather than
:class:`~shared_core.security.apikey.ApiKeyRecord` (that dataclass is
immutable/caller-owned storage; this service already has a database).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError
from shared_core.security.apikey import create_api_key, hash_api_key

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.apikey import ApiKey
from app.repositories.apikey import ApiKeyRepository

_KEY_PREFIX_LENGTH = 12


class ApiKeyService:
    """Creates, lists, and revokes API keys."""

    def __init__(self, api_keys: ApiKeyRepository) -> None:
        self._api_keys = api_keys

    async def create(
        self, user_id: UUID, *, name: str, scopes: list[str], expires_in_days: int | None
    ) -> tuple[ApiKey, str]:
        """Create a new API key for *user_id*, returning ``(record, raw_key)``.

        *raw_key* is returned exactly once; only its hash is persisted.
        """
        raw_key, record = create_api_key(scopes=scopes, ttl_days=expires_in_days)
        api_key = await self._api_keys.create(
            ApiKey(
                user_id=user_id,
                name=name,
                key_prefix=raw_key[:_KEY_PREFIX_LENGTH],
                hashed_key=record.hashed_key,
                scopes=",".join(scopes),
                expires_at=record.expires_at,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        return api_key, raw_key

    async def authenticate(self, raw_key: str) -> ApiKey | None:
        """Look up and validate a presented raw API key, returning its record if usable."""
        record = await self._api_keys.get_by_hashed_key(hash_api_key(raw_key))
        if record is None or record.revoked_at is not None:
            return None
        if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
            return None
        record.last_used_at = datetime.now(UTC)
        return record

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        """Every API key belonging to *user_id* ("GET /auth/apikeys")."""
        return await self._api_keys.list_for_user(user_id)

    async def revoke(self, user_id: UUID, api_key_id: UUID) -> None:
        """Revoke *user_id*'s API key with id *api_key_id* ("Revocation").

        Raises:
            NotFoundError: If no such key belongs to *user_id*.
        """
        record = await self._api_keys.require_by_id(api_key_id)
        if record.user_id != user_id:
            raise NotFoundError(f"API key '{api_key_id}' was not found.")
        record.revoked_at = datetime.now(UTC)


__all__ = ["ApiKeyService"]
