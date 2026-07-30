"""Quotas as a service: define budgets, report headroom, warn early.

The arithmetic lives in :mod:`app.quotas.engine`; enforcement happens
inside :class:`~app.services.decision.DecisionService`, which is the only
place that consumes. This service is the management surface -- defining
limits, reading usage, and raising the warning that gives an operator
time to act.

**The warning fires once per period.** A quota that notified on every
request past 80% would be a quota nobody reads the notifications from,
which is the same as a quota that never warns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.policy_events import SOURCE_SERVICE, QuotaExceededEvent
from app.models.enums import QuotaPeriod, QuotaScope
from app.models.governance import PolicyQuota
from app.notifications.policy_notifications import PolicyNotificationService
from app.quotas import engine as quotas
from app.repositories.runtime import PolicyQuotaRepository
from app.types import EventPublisher

logger = get_logger("app.services.quota")


def period_of(record: PolicyQuota) -> QuotaPeriod:
    """A quota's period as a genuine enum member.

    ``period`` is annotated ``Mapped[QuotaPeriod]`` but stored in a
    ``String``, so a row loaded from Postgres yields a plain ``str``.
    """
    value = record.period
    return value if isinstance(value, QuotaPeriod) else QuotaPeriod(value)


def scope_of(record: PolicyQuota) -> QuotaScope:
    """A quota's scope as a genuine enum member."""
    value = record.scope
    return value if isinstance(value, QuotaScope) else QuotaScope(value)


class QuotaService:
    """Defines and reports consumption budgets."""

    def __init__(
        self,
        quota_repository: PolicyQuotaRepository,
        notifications: PolicyNotificationService,
        *,
        publish_event: EventPublisher,
        warning_threshold: float = 0.8,
    ) -> None:
        self._quotas = quota_repository
        self._notifications = notifications
        self._publish_event = publish_event
        self._warning_threshold = warning_threshold

    async def define(
        self,
        organization_id: UUID,
        *,
        scope: QuotaScope,
        scope_id: str,
        resource: str,
        limit_value: float,
        period: QuotaPeriod = QuotaPeriod.MONTHLY,
        is_hard_limit: bool = True,
        policy_id: UUID | None = None,
        description: str | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyQuota:
        """Create a budget.

        Raises:
            ConflictError: If one already exists for this scope and
                resource. Refused rather than merged: two quotas for the
                same thing have no defined combination, and silently
                overwriting the existing limit would change enforcement
                without anybody asking for it.
            ValidationError: If the limit is negative.
        """
        if limit_value < 0:
            raise ValidationError(
                f"A quota limit cannot be negative, got {limit_value}. Use 0 for "
                "unlimited, or a DENY policy to refuse the operation outright."
            )

        existing = await self._quotas.get_one(
            organization_id, scope=scope, scope_id=scope_id, resource=resource
        )
        if existing is not None:
            raise ConflictError(
                f"A {period!s} quota for {resource!r} already exists on "
                f"{scope!s}:{scope_id}. Update it rather than defining a second."
            )

        now = datetime.now(UTC)
        return await self._quotas.create(
            PolicyQuota(
                organization_id=organization_id,
                policy_id=policy_id,
                scope=scope,
                scope_id=scope_id,
                resource=resource,
                limit_value=limit_value,
                consumed=0.0,
                period=period,
                period_started_at=quotas.period_start(now, period),
                is_hard_limit=is_hard_limit,
                description=description,
                created_by=actor_id,
            )
        )

    async def update_limit(
        self,
        organization_id: UUID,
        *,
        scope: QuotaScope,
        scope_id: str,
        resource: str,
        limit_value: float | None = None,
        is_hard_limit: bool | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyQuota:
        """Change a budget's ceiling or hardness.

        Consumption is deliberately untouched. Raising a limit should let
        already-blocked work through immediately; resetting consumption
        at the same time would also forgive what has already been used,
        which is a different decision nobody made.

        Raises:
            NotFoundError: If no such quota exists.
            ValidationError: If the new limit is negative.
        """
        stored = await self._quotas.get_one(
            organization_id, scope=scope, scope_id=scope_id, resource=resource
        )
        if stored is None:
            raise NotFoundError(f"No quota for {resource!r} on {scope!s}:{scope_id}.")
        if limit_value is not None:
            if limit_value < 0:
                raise ValidationError(f"A quota limit cannot be negative, got {limit_value}.")
            stored.limit_value = limit_value
            # Cleared so a quota raised above its consumption starts
            # warning again from the new threshold rather than staying
            # silent because it warned under the old one.
            stored.warning_sent_at = None
            stored.exceeded_at = None
        if is_hard_limit is not None:
            stored.is_hard_limit = is_hard_limit
        stored.updated_by = actor_id
        return await self._quotas.update(stored)

    async def reset(
        self,
        organization_id: UUID,
        *,
        scope: QuotaScope,
        scope_id: str,
        resource: str,
    ) -> PolicyQuota:
        """Zero a budget's consumption and start a fresh period.

        Raises:
            NotFoundError: If no such quota exists.
        """
        stored = await self._quotas.get_one(
            organization_id, scope=scope, scope_id=scope_id, resource=resource
        )
        if stored is None:
            raise NotFoundError(f"No quota for {resource!r} on {scope!s}:{scope_id}.")
        now = datetime.now(UTC)
        await self._quotas.reset_period(
            stored.id, period_started_at=quotas.period_start(now, period_of(stored))
        )
        return await self._quotas.require_by_id(stored.id)

    async def state_for(
        self,
        organization_id: UUID,
        *,
        scopes: list[tuple[QuotaScope, str]],
        resource: str | None = None,
    ) -> list[quotas.QuotaState]:
        """Current standing of every budget matching these scopes."""
        rows = await self._quotas.list_applicable(organization_id, scopes=scopes, resource=resource)
        return [quotas.state_from_row(one) for one in rows]

    async def list_quotas(self, organization_id: UUID, *, limit: int = 200) -> list[PolicyQuota]:
        """Every budget an organization has defined."""
        return await self._quotas.list_for_org(organization_id, limit=limit)

    async def report_exhaustion(
        self,
        organization_id: UUID,
        state: quotas.QuotaState,
        *,
        quota_id: UUID,
        notify_user_id: str | None = None,
    ) -> None:
        """Record and announce that a budget blocked something."""
        now = datetime.now(UTC)
        await self._quotas.record_exceeded(quota_id, moment=now)
        await self._publish_event(
            QuotaExceededEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "scope": state.scope,
                    "resource": state.resource,
                    "limit": state.limit_value,
                    "consumed": state.consumed,
                    "period": str(state.period),
                },
            )
        )
        if notify_user_id:
            await self._notifications.send_quota_exceeded(
                notify_user_id,
                resource=state.resource,
                consumed=state.consumed,
                limit=state.limit_value,
            )

    async def maybe_warn(
        self,
        organization_id: UUID,
        *,
        notify_user_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Warn about budgets approaching their limit, once per period.

        The once-per-period guard is what makes the warning readable: one
        that fired on every request past the threshold would be a
        notification stream nobody opens, which is the same as no
        warning at all.
        """
        rows = await self._quotas.list_for_org(organization_id, limit=limit)
        warned: list[dict[str, Any]] = []
        now = datetime.now(UTC)

        for row in rows:
            state = quotas.state_from_row(row)
            if state.unlimited or state.usage_ratio < self._warning_threshold:
                continue
            if row.warning_sent_at is not None:
                continue

            percent = round(state.usage_ratio * 100)
            row.warning_sent_at = now
            await self._quotas.update(row)
            if notify_user_id:
                await self._notifications.send_quota_warning(
                    notify_user_id, resource=state.resource, percent=percent
                )
            warned.append(
                {
                    "scope": state.scope,
                    "resource": state.resource,
                    "percent": percent,
                    "consumed": state.consumed,
                    "limit": state.limit_value,
                }
            )

        if warned:
            logger.info(
                "Warned about quotas approaching their limits.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "warned": len(warned),
                    }
                },
            )
        return warned

    async def sweep_periods(self, organization_id: UUID, *, limit: int = 500) -> int:
        """Roll over any budget whose period has ended; returns how many.

        A backstop, not the primary mechanism: enforcement rolls a period
        over lazily when it reads a stale quota, so this only catches
        budgets nothing has touched since their period ended. Without it,
        an idle tenant's usage figures would keep reporting last month's
        numbers.
        """
        rows = await self._quotas.list_for_org(organization_id, limit=limit)
        now = datetime.now(UTC)
        rolled = 0
        for row in rows:
            state = quotas.state_from_row(row)
            if quotas.needs_reset(state, now=now):
                await self._quotas.reset_period(
                    row.id, period_started_at=quotas.period_start(now, state.period)
                )
                rolled += 1
        return rolled


__all__ = ["QuotaService", "period_of", "scope_of"]
