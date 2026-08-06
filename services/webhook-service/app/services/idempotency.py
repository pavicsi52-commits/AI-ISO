"""Idempotency-key tracking (docs/057 "IDEMPOTENCY").

A genuine gap -- `shared_core` has only a bare header-name constant
(``HEADER_IDEMPOTENCY_KEY``), no duplicate-detection logic. Built new
against this service's own ``webhook_idempotency`` table: a caller that
retries the same request with the same key gets back the exact result
recorded for the first attempt, rather than re-processing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.models.enums import IdempotencyStatus
from app.models.idempotency import WebhookIdempotencyKey
from app.repositories.idempotency import WebhookIdempotencyKeyRepository


@dataclass(frozen=True, slots=True)
class IdempotencyCheck:
    """The outcome of checking one idempotency key."""

    is_duplicate: bool
    existing_response: dict[str, Any] | None


class IdempotencyService:
    """Caller-supplied idempotency keys: duplicate detection and result replay."""

    def __init__(self, keys: WebhookIdempotencyKeyRepository, *, ttl_seconds: int) -> None:
        self._keys = keys
        self._ttl_seconds = ttl_seconds

    async def check(self, organization_id: UUID, idempotency_key: str) -> IdempotencyCheck:
        """Whether *idempotency_key* has already been settled for this organization.

        A key still ``PENDING`` (a concurrent request is mid-flight) is
        treated as *not yet* a duplicate -- there is no settled result to
        replay yet, so the caller proceeds and will race the other
        request to actually settle the key.
        """
        existing = await self._keys.get_by_key(organization_id, idempotency_key)
        if existing is None or existing.status != IdempotencyStatus.COMPLETED:
            return IdempotencyCheck(is_duplicate=False, existing_response=None)
        return IdempotencyCheck(is_duplicate=True, existing_response=existing.response_snapshot)

    async def reserve(self, organization_id: UUID, idempotency_key: str) -> WebhookIdempotencyKey:
        """Record *idempotency_key* as pending, before processing begins."""
        now = datetime.now(UTC)
        return await self._keys.create(
            WebhookIdempotencyKey(
                organization_id=organization_id,
                idempotency_key=idempotency_key,
                status=IdempotencyStatus.PENDING,
                expires_at=now + timedelta(seconds=self._ttl_seconds),
            )
        )

    async def settle(
        self, organization_id: UUID, idempotency_key: str, *, response_snapshot: dict[str, Any]
    ) -> WebhookIdempotencyKey | None:
        """Record the settled result for *idempotency_key*, if it is still tracked."""
        existing = await self._keys.get_by_key(organization_id, idempotency_key)
        if existing is None:
            return None
        existing.status = IdempotencyStatus.COMPLETED
        existing.response_snapshot = dict(response_snapshot)
        return await self._keys.update(existing)

    async def expire_due(self, *, now: datetime, limit: int = 500) -> int:
        """Mark every key whose own expiry has passed as ``EXPIRED``. Returns how many."""
        rows = await self._keys.list_expired(now=now, limit=limit)
        for row in rows:
            row.status = IdempotencyStatus.EXPIRED
            await self._keys.update(row)
        return len(rows)


__all__ = ["IdempotencyCheck", "IdempotencyService"]
