"""API key lifecycle: generation, rotation, revocation, and verification.

Thin adapter onto `shared_core.security.apikey` (Prompt 017) -- this
service is the durable persistence behind that otherwise-stateless
generate/hash/rotate/revoke/check module, per this prompt's own "use
every previously implemented platform framework" instruction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.apikey import (
    ApiKeyRecord,
    check_api_key_ip_allowed,
    check_api_key_scope,
    create_api_key,
    hash_api_key,
    is_api_key_usable,
    record_api_key_usage,
    revoke_api_key,
    rotate_api_key,
)

from app.models.apikey import ApiKey
from app.models.enums import ApiKeyStatus
from app.repositories.apikey import ApiKeyRepository


def _row_to_record(row: ApiKey) -> ApiKeyRecord:
    """Rebuild the `shared_core` value object from a persisted row."""
    return ApiKeyRecord(
        key_id=row.key_id,
        hashed_key=row.hashed_key,
        scopes=frozenset(row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked=row.status == ApiKeyStatus.REVOKED,
        ip_allowlist=frozenset(row.ip_allowlist),
    )


class ApiKeyService:
    """API keys: creation, rotation, revocation, and verification."""

    def __init__(self, api_keys: ApiKeyRepository) -> None:
        self._api_keys = api_keys

    async def create(
        self,
        organization_id: UUID,
        *,
        client_id: UUID,
        name: str,
        scopes: list[str] | None = None,
        ttl_days: int | None = None,
        ip_allowlist: list[str] | None = None,
        actor_id: str | None = None,
    ) -> tuple[str, ApiKey]:
        """Issue a new API key.

        Returns the raw key (shown to the caller exactly once) and the
        persisted row (which only ever stores its hash).
        """
        raw_key, record = create_api_key(
            scopes=scopes or (), ttl_days=ttl_days, ip_allowlist=ip_allowlist or ()
        )
        stored = await self._api_keys.create(
            ApiKey(
                organization_id=organization_id,
                client_id=client_id,
                key_id=record.key_id,
                hashed_key=record.hashed_key,
                name=name,
                scopes=list(record.scopes),
                ip_allowlist=list(record.ip_allowlist),
                status=ApiKeyStatus.ACTIVE,
                expires_at=record.expires_at,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )
        return raw_key, stored

    async def get(self, organization_id: UUID, api_key_id: UUID) -> ApiKey:
        """One key.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._api_keys.require_in_org(organization_id, api_key_id)

    async def list_for_client(self, organization_id: UUID, client_id: UUID) -> list[ApiKey]:
        """Every key issued to one client."""
        return await self._api_keys.list_for_client(organization_id, client_id)

    async def rotate(
        self, organization_id: UUID, api_key_id: UUID, *, actor_id: str | None = None
    ) -> tuple[str, ApiKey]:
        """Rotate a key: the old one stops working, a new secret takes its place.

        Returns the new raw key and the updated row.
        """
        stored = await self._api_keys.require_in_org(organization_id, api_key_id)
        old_record = _row_to_record(stored)
        # `rotate_api_key` returns `(new_raw_key, new_record, revoked_old_record)` --
        # the old record is returned only so a caller storing keys as
        # separate rows can persist its revocation; this service rotates
        # in place on the same row, so the old record itself is unused.
        new_raw_key, new_record, _revoked_old_record = rotate_api_key(old_record)
        stored.key_id = new_record.key_id
        stored.hashed_key = new_record.hashed_key
        stored.expires_at = new_record.expires_at
        stored.status = ApiKeyStatus.ACTIVE
        stored.revoked_at = None
        stored.updated_by = UUID(actor_id) if actor_id else None
        updated = await self._api_keys.update(stored)
        return new_raw_key, updated

    async def revoke(
        self, organization_id: UUID, api_key_id: UUID, *, actor_id: str | None = None
    ) -> ApiKey:
        """Revoke a key immediately."""
        stored = await self._api_keys.require_in_org(organization_id, api_key_id)
        revoke_api_key(_row_to_record(stored))
        stored.status = ApiKeyStatus.REVOKED
        stored.revoked_at = datetime.now(UTC)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._api_keys.update(stored)

    async def verify(
        self, raw_key: str, *, required_scope: str | None = None, source_ip: str | None = None
    ) -> ApiKey:
        """Verify a raw API key presented by a caller.

        Raises:
            AuthenticationError: If the key is unknown, expired, revoked,
                scope-insufficient, or the caller's IP is not allowlisted.
        """
        hashed = hash_api_key(raw_key)
        stored = await self._api_keys.get_by_hashed_key(hashed)
        if stored is None:
            raise AuthenticationError("Invalid API key.")
        record = _row_to_record(stored)
        if not is_api_key_usable(record):
            raise AuthenticationError("This API key is expired or revoked.")
        if required_scope is not None and not check_api_key_scope(record, required_scope):
            raise AuthenticationError(f"This API key lacks the required scope: {required_scope!r}.")
        if (
            source_ip is not None
            and record.ip_allowlist
            and not check_api_key_ip_allowed(record, source_ip)
        ):
            raise AuthenticationError("This API key is not allowlisted for the caller's IP.")
        updated_record = record_api_key_usage(record)
        stored.last_used_at = updated_record.last_used_at
        await self._api_keys.update(stored)
        return stored


__all__ = ["ApiKeyService"]
