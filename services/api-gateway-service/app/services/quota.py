"""Quota configuration and enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import QuotaKind, QuotaPeriod, QuotaScope
from app.models.quota import ApiQuotaPolicy
from app.ratelimiting import engine as ratelimiting_engine
from app.repositories.quota import ApiQuotaPolicyRepository


class QuotaService:
    """Quotas: configuration, usage tracking, and periodic reset."""

    def __init__(self, quotas: ApiQuotaPolicyRepository) -> None:
        self._quotas = quotas

    async def set_policy(
        self,
        organization_id: UUID,
        *,
        scope: QuotaScope,
        scope_reference: str | None,
        kind: QuotaKind,
        period: QuotaPeriod,
        limit_value: float,
    ) -> ApiQuotaPolicy:
        """Create or replace the quota for this exact scope/reference/kind."""
        existing = await self._quotas.find(organization_id, scope, scope_reference, kind)
        if existing is None:
            now = datetime.now(UTC)
            start, end = ratelimiting_engine.quota_period_bounds(period, now)
            return await self._quotas.create(
                ApiQuotaPolicy(
                    organization_id=organization_id,
                    scope=scope,
                    scope_reference=scope_reference,
                    kind=kind,
                    period=period,
                    limit_value=limit_value,
                    used_value=0.0,
                    period_started_at=start,
                    period_resets_at=end,
                )
            )
        existing.period = period
        existing.limit_value = limit_value
        return await self._quotas.update(existing)

    async def list_policies(self, organization_id: UUID) -> list[ApiQuotaPolicy]:
        """Every quota configured in this organization."""
        return await self._quotas.list_for_org(organization_id)

    async def check_and_increment(
        self,
        organization_id: UUID,
        scope: QuotaScope,
        scope_reference: str | None,
        kind: QuotaKind,
        *,
        amount: float = 1.0,
    ) -> bool:
        """Whether this call is within quota -- and if so, records its usage.

        A scope with no configured quota is unlimited. Returns ``True``
        (and increments usage) if allowed; ``False`` (usage untouched)
        if the quota is already exhausted. A quota whose tracked period
        has already ended is reset to a fresh, empty period first, so a
        caller is never refused against a stale window.
        """
        policy = await self._quotas.find(organization_id, scope, scope_reference, kind)
        if policy is None or not policy.enabled:
            return True
        now = datetime.now(UTC)
        if ratelimiting_engine.is_period_expired(policy.period_resets_at, now=now):
            start, end = ratelimiting_engine.quota_period_bounds(policy.period, now)
            policy.used_value = 0.0
            policy.period_started_at = start
            policy.period_resets_at = end
        if ratelimiting_engine.is_quota_exceeded(
            used_value=policy.used_value, limit_value=policy.limit_value
        ):
            await self._quotas.update(policy)
            return False
        policy.used_value += amount
        await self._quotas.update(policy)
        return True

    async def reset_due(self, *, now: datetime, limit: int = 500) -> int:
        """Reset every quota whose period has ended, across every organization.

        The quota-reset sweep's own entry point.
        """
        due = await self._quotas.list_due_for_reset(now=now, limit=limit)
        for policy in due:
            start, end = ratelimiting_engine.quota_period_bounds(policy.period, now)
            policy.used_value = 0.0
            policy.period_started_at = start
            policy.period_resets_at = end
            await self._quotas.update(policy)
        return len(due)


__all__ = ["QuotaService"]
