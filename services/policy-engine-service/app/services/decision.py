"""The decision service: the endpoint every other service calls.

Assembles a catalogue, applies exceptions and quotas, runs the pure
engine, records the answer, and returns it.

The order of the four gates is the design, and each one is placed where
it is for a reason:

1. **Quotas first.** Cheapest, and a budget refusal needs no policy
   evaluation to justify it. It also means an exhausted tenant cannot
   drive evaluation load by hammering a denied endpoint.
2. **Then the policy engine**, over published policies only.
3. **Then exceptions**, which can waive a *deny* -- and only a deny.
   An exception that could waive an approval requirement would be an
   approval by another name, granted without the sign-off the policy
   asked for.
4. **Then obligations**, turning a REQUIRE_APPROVAL effect into an
   actual pending approval somebody can act on.

**A recorded decision is evidence.** It carries the effect, the policies
that produced it, the trace, and a redacted snapshot of the attributes
that were seen -- because the question asked afterwards is never "what
did it decide" but "why", months later, by somebody who was not there.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.attributes.resolver import EvaluationContext
from app.evaluation.engine import Decision, EvaluablePolicy, evaluate, policy_from_row
from app.models.decision import PolicyDecision, PolicyException
from app.models.enums import (
    DENYING_EFFECTS,
    PERMITTING_EFFECTS,
    ActionType,
    PolicyEffect,
    QuotaScope,
    ResourceType,
    SubjectType,
)
from app.quotas import engine as quotas
from app.repositories.policy import PolicyAttributeRepository, PolicyRepository
from app.repositories.runtime import (
    PolicyDecisionRepository,
    PolicyExceptionRepository,
    PolicyQuotaRepository,
)

logger = get_logger("app.services.decision")

REDACTED = "***REDACTED***"


@dataclass(slots=True)
class DecisionRequest:
    """One authorization question."""

    organization_id: UUID
    subject_type: SubjectType
    subject_id: str
    resource_type: ResourceType
    action: ActionType
    resource_id: str | None = None
    context: EvaluationContext = field(default_factory=EvaluationContext)
    project_id: str | None = None
    request_id: str | None = None
    quota_amount: float = 1.0
    quota_resource: str | None = None

    def quota_scopes(self) -> list[tuple[QuotaScope, str]]:
        """Every budget this request is counted against.

        A request usually sits inside several at once -- the
        organization's, the project's, and the user's. All of them are
        checked, because returning only the narrowest would let a user
        inside their personal limit blow through the organization's.
        """
        scopes: list[tuple[QuotaScope, str]] = [
            (QuotaScope.ORGANIZATION, str(self.organization_id)),
            (QuotaScope.USER, self.subject_id),
        ]
        if self.project_id:
            scopes.append((QuotaScope.PROJECT, self.project_id))
        return scopes


def redact(context: EvaluationContext, sensitive: set[tuple[str, str]]) -> dict[str, Any]:
    """A stored snapshot with sensitive attributes masked.

    A trace records what each condition saw, which is the point -- but
    for an authentication token or a personal identifier it would turn
    the decision log into a second copy of data that is protected
    elsewhere, under different rules, for a different retention period.
    """
    payload = context.as_dict()
    for source, path in sensitive:
        bucket = payload.get(source)
        if not isinstance(bucket, dict):
            continue
        segments = path.split(".")
        current: Any = bucket
        for segment in segments[:-1]:
            if not isinstance(current, dict) or segment not in current:
                current = None
                break
            current = current[segment]
        if isinstance(current, dict) and segments[-1] in current:
            current[segments[-1]] = REDACTED
    return payload


class DecisionService:
    """Answers authorization questions and records the answers."""

    def __init__(
        self,
        policies: PolicyRepository,
        decisions: PolicyDecisionRepository,
        exceptions: PolicyExceptionRepository,
        quota_repository: PolicyQuotaRepository,
        attributes: PolicyAttributeRepository,
        *,
        default_effect: PolicyEffect = PolicyEffect.DENY,
        fail_closed: bool = True,
        max_policies: int = 500,
        quota_enforcement: bool = True,
        quota_warning_threshold: float = 0.8,
        slow_threshold_ms: int = 2_000,
    ) -> None:
        self._policies = policies
        self._decisions = decisions
        self._exceptions = exceptions
        self._quotas = quota_repository
        self._attributes = attributes
        self._default_effect = default_effect
        self._fail_closed = fail_closed
        self._max_policies = max_policies
        self._quota_enforcement = quota_enforcement
        self._quota_warning_threshold = quota_warning_threshold
        self._slow_threshold_ms = slow_threshold_ms

    async def decide(
        self,
        request: DecisionRequest,
        *,
        actor_id: UUID | None = None,
        record: bool = True,
        consume_quota: bool = True,
    ) -> tuple[Decision, PolicyDecision | None]:
        """Answer one request and, unless told otherwise, record it.

        Returns the decision and its stored row. ``record=False`` is for
        a dry-run check a caller makes before deciding whether to try
        something -- it must not pollute the decision log or the
        statistics derived from it.
        """
        started = time.perf_counter()
        warnings: list[str] = []

        quota_check = await self._check_quotas(request)
        if not quota_check.permitted:
            decision = Decision(
                effect=quota_check.effect,
                reason=quota_check.reason,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            decision.errors.extend(quota_check.warnings)
            stored = await self._record(request, decision, actor_id) if record else None
            return decision, stored
        warnings.extend(quota_check.warnings)

        catalogue = await self._load_catalogue(request.organization_id)
        decision = evaluate(
            catalogue,
            request.context,
            subject_type=request.subject_type,
            resource_type=request.resource_type,
            action=request.action,
            default_effect=self._default_effect,
            fail_closed=self._fail_closed,
            max_policies=self._max_policies,
        )

        if decision.effect in DENYING_EFFECTS:
            decision = await self._apply_exceptions(request, decision)

        decision.duration_ms = (time.perf_counter() - started) * 1000
        decision.errors.extend(warnings)

        if decision.duration_ms > self._slow_threshold_ms:
            # Reported, never enforced as a timeout. Cancelling an
            # authorization decision halfway leaves the caller with no
            # answer at all, which is worse than a slow one -- but a
            # pathological policy needs to be visible before it is
            # load-bearing.
            logger.warning(
                "A policy decision exceeded its latency budget.",
                extra={
                    "extra_fields": {
                        "organization_id": str(request.organization_id),
                        "duration_ms": round(decision.duration_ms, 2),
                        "budget_ms": self._slow_threshold_ms,
                        "policies_considered": decision.policies_considered,
                    }
                },
            )

        if consume_quota and decision.effect in PERMITTING_EFFECTS:
            # Consumed only for a request that may actually proceed. A
            # refused request that still burned budget would let anyone
            # exhaust a tenant's quota by making requests they were never
            # permitted to make.
            await self._consume_quotas(request)

        stored = await self._record(request, decision, actor_id) if record else None
        return decision, stored

    async def _load_catalogue(
        self, organization_id: UUID, *, extra_policy_ids: list[UUID] | None = None
    ) -> list[EvaluablePolicy]:
        """Published policies, plus any named drafts, in evaluable form.

        A policy whose stored rule will not rebuild is skipped and
        logged rather than allowed to fail the whole decision -- but the
        skip is loud, because a governance rule that silently stopped
        applying is the failure this service exists to prevent.
        """
        rows = await self._policies.list_evaluable(organization_id, limit=self._max_policies)
        if extra_policy_ids:
            drafts = await self._policies.list_by_ids(organization_id, extra_policy_ids)
            known = {row.id for row in rows}
            rows.extend(one for one in drafts if one.id not in known)

        catalogue: list[EvaluablePolicy] = []
        for row in rows:
            try:
                catalogue.append(policy_from_row(row))
            except Exception as exc:
                logger.error(
                    "A stored policy could not be loaded and was skipped; it is not "
                    "influencing decisions.",
                    extra={
                        "extra_fields": {
                            "policy_id": str(row.id),
                            "slug": row.slug,
                            "error": str(exc),
                        }
                    },
                )
        return catalogue

    async def _check_quotas(self, request: DecisionRequest) -> quotas.QuotaCheck:
        """Whether the request fits inside every budget that applies."""
        rows = await self._quotas.list_applicable(
            request.organization_id,
            scopes=request.quota_scopes(),
            resource=request.quota_resource,
        )
        now = datetime.now(UTC)
        states: list[quotas.QuotaState] = []
        for row in rows:
            state = quotas.state_from_row(row)
            if quotas.needs_reset(state, now=now):
                # Rolled over lazily, on read. A background sweep would
                # leave a window in which a new period is enforced
                # against last period's consumption -- refusing requests
                # that have a full budget available.
                await self._quotas.reset_period(
                    row.id, period_started_at=quotas.period_start(now, state.period)
                )
                state = quotas.QuotaState(
                    scope=state.scope,
                    resource=state.resource,
                    limit_value=state.limit_value,
                    consumed=0.0,
                    period=state.period,
                    is_hard_limit=state.is_hard_limit,
                    period_started_at=quotas.period_start(now, state.period),
                )
            states.append(state)

        return quotas.check(
            states,
            amount=request.quota_amount,
            warning_threshold=self._quota_warning_threshold,
            enforcement_enabled=self._quota_enforcement,
        )

    async def _consume_quotas(self, request: DecisionRequest) -> None:
        """Add this request to every budget it counts against."""
        rows = await self._quotas.list_applicable(
            request.organization_id,
            scopes=request.quota_scopes(),
            resource=request.quota_resource,
        )
        for row in rows:
            await self._quotas.consume(row.id, request.quota_amount)

    async def _apply_exceptions(self, request: DecisionRequest, decision: Decision) -> Decision:
        """Waive a denial if a live, scoped exception covers it.

        **Only a denial.** An exception that could waive
        ``REQUIRE_APPROVAL`` would be an approval by another name,
        granted without the sign-off the policy asked for -- and unlike
        an approval it would leave no record of who agreed, only of who
        wrote the waiver.
        """
        if decision.deciding_policy_id is None:
            return decision

        live = await self._exceptions.list_active(
            request.organization_id,
            policy_id=UUID(decision.deciding_policy_id),
            moment=datetime.now(UTC),
        )
        covering = next((one for one in live if self._exception_covers(one, request)), None)
        if covering is None:
            return decision

        await self._exceptions.record_use(covering.id)
        logger.info(
            "A policy denial was waived by an active exception.",
            extra={
                "extra_fields": {
                    "policy_id": decision.deciding_policy_id,
                    "exception_id": str(covering.id),
                    "expires_at": covering.expires_at.isoformat(),
                }
            },
        )
        decision.effect = PolicyEffect.CONDITIONAL_ALLOW
        decision.reason = (
            f"{decision.reason} Waived by exception {covering.id} "
            f"({covering.reason}), which expires {covering.expires_at.isoformat()}."
        )
        decision.obligations = {
            **decision.obligations,
            "exception_id": str(covering.id),
            "exception_expires_at": covering.expires_at.isoformat(),
        }
        return decision

    @staticmethod
    def _exception_covers(exception: PolicyException, request: DecisionRequest) -> bool:
        """Whether a waiver's scope admits this request.

        An empty field means "any", matching how policy selectors work.
        A waiver naming neither a subject nor a resource is deliberately
        broad -- and that is exactly why it still expires and is still
        counted every time it is relied on.
        """
        if exception.subject_id and exception.subject_id != request.subject_id:
            return False
        if exception.resource_id and exception.resource_id != request.resource_id:
            return False
        return not (
            exception.resource_type and str(exception.resource_type) != str(request.resource_type)
        )

    async def _record(
        self, request: DecisionRequest, decision: Decision, actor_id: UUID | None
    ) -> PolicyDecision | None:
        """Store one decision, best-effort.

        Swallowed on failure, and this is the one trade-off in this file
        worth arguing about. Refusing to answer an authorization question
        because the decision log is unavailable would take the whole
        platform down with it -- every protected operation everywhere
        calls this. The cost is a gap in the evidence; the alternative is
        an outage.
        """
        try:
            sensitive = await self._attributes.sensitive_paths(request.organization_id)
            return await self._decisions.create(
                PolicyDecision(
                    organization_id=request.organization_id,
                    request_id=request.request_id,
                    subject_type=request.subject_type,
                    subject_id=request.subject_id,
                    resource_type=request.resource_type,
                    resource_id=request.resource_id,
                    action=request.action,
                    effect=decision.effect,
                    permitted=decision.permitted,
                    reason=decision.reason,
                    matched_policy_ids=decision.matched_policy_ids,
                    deciding_policy_id=(
                        UUID(decision.deciding_policy_id) if decision.deciding_policy_id else None
                    ),
                    evaluation_trace={"policies": [one.as_dict() for one in decision.outcomes]},
                    obligations=decision.obligations,
                    risk_score=decision.risk_score,
                    context_snapshot=redact(request.context, sensitive),
                    duration_ms=decision.duration_ms,
                    policies_considered=decision.policies_considered,
                    decided_at=datetime.now(UTC),
                    error="; ".join(decision.errors) if decision.errors else None,
                    created_by=actor_id,
                )
            )
        except Exception as exc:
            logger.error(
                "Could not record a policy decision; the decision itself still stands.",
                extra={
                    "extra_fields": {
                        "organization_id": str(request.organization_id),
                        "effect": str(decision.effect),
                        "error": str(exc),
                    }
                },
            )
            return None

    async def history(
        self,
        organization_id: UUID,
        *,
        effect: PolicyEffect | None = None,
        subject_id: str | None = None,
        denied_only: bool = False,
        limit: int = 200,
    ) -> list[PolicyDecision]:
        """Recorded decisions, most recent first."""
        return await self._decisions.list_for_org(
            organization_id,
            effect=effect,
            subject_id=subject_id,
            denied_only=denied_only,
            limit=limit,
        )

    async def by_request_id(self, organization_id: UUID, request_id: str) -> PolicyDecision | None:
        """The decision behind one correlation id."""
        return await self._decisions.get_by_request_id(organization_id, request_id)


__all__ = ["REDACTED", "DecisionRequest", "DecisionService", "redact"]
