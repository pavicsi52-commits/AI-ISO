"""Service account lifecycle.

Per docs/030 "SERVICE ACCOUNTS": Machine Accounts, Token
Authentication, Scoped Permissions, Rotation, Audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.security.apikey import generate_api_key, hash_api_key

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.service_account import ServiceAccount
from app.repositories.service_account import ServiceAccountRepository


class ServiceAccountService:
    """Creates, authenticates, and rotates service account tokens."""

    def __init__(self, service_accounts: ServiceAccountRepository) -> None:
        self._service_accounts = service_accounts

    async def create(
        self, *, name: str, description: str | None, scopes: list[str]
    ) -> tuple[ServiceAccount, str]:
        """Create a new service account, returning ``(record, raw_token)``."""
        raw_token = generate_api_key()
        record = await self._service_accounts.create(
            ServiceAccount(
                name=name,
                description=description,
                hashed_token=hash_api_key(raw_token),
                scopes=",".join(scopes),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        return record, raw_token

    async def authenticate(self, raw_token: str) -> ServiceAccount | None:
        """Look up and validate a presented raw service account token."""
        record = await self._service_accounts.get_by_hashed_token(hash_api_key(raw_token))
        if record is None or not record.is_enabled:
            return None
        record.last_used_at = datetime.now(UTC)
        return record

    async def rotate(self, service_account_id: UUID) -> tuple[ServiceAccount, str]:
        """Issue a new token for an existing service account, invalidating the old one.

        Covers "Rotation".
        """
        record = await self._service_accounts.require_by_id(service_account_id)
        raw_token = generate_api_key()
        record.hashed_token = hash_api_key(raw_token)
        record.rotated_at = datetime.now(UTC)
        return record, raw_token

    async def disable(self, service_account_id: UUID) -> None:
        """Disable a service account without deleting its audit history."""
        record = await self._service_accounts.require_by_id(service_account_id)
        record.is_enabled = False


__all__ = ["ServiceAccountService"]
