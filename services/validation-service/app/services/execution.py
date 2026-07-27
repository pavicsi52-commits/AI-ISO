"""The validation execution orchestrator. Per docs/043 "VALIDATION
ENGINE": Sequential Checks, Parallel Checks, Conditional Checks, Rule
Chaining, Reusable Check Libraries, Retry, Timeout, Cancellation,
Execution Priorities, Checkpoint Support.

Runs every ``(check, target)`` pair in a profile's own resolved
``check_ids`` x an execution's own ``target_ids``, respecting
``concurrency_strategy`` (``SEQUENTIAL`` runs one pair at a time;
``PARALLEL``/``DISTRIBUTED`` both run bounded-concurrency via
``asyncio.Semaphore`` within this one process -- true multi-process
"Distributed Execution" would need a worker pool this service doesn't
have, an honest scope limit documented here rather than silently
implied). Cancellation is cooperative: :meth:`cancel` only flips the
row's own ``status`` to ``CANCELLED``; the run loop notices on its own
next iteration boundary, the same "cooperative, not preemptive"
limitation ``services/workflow-runtime-service``'s own
``WorkflowInstanceService`` already documents for an identical reason
(there is no true interrupt mechanism for work already in flight).

"Checkpoint Support"/"Execution Priorities" are honest platform gaps:
each ``(check, target)`` pair is small and fast enough (an HTTP call or
two, never a long-running remote job) that resuming a partially-run
execution from a checkpoint has no real value over simply re-running
it, and "Retry"/"Timeout" are already covered per-check via
``ValidationCheck.retry_count``/``timeout_seconds`` rather than needing
their own execution-level mechanism.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.workflow_client import WorkflowRuntimeClient
from app.collectors.context import CollectorContext
from app.collectors.registry import CollectorRegistry
from app.events.validation_events import (
    ValidationCancelledEvent,
    ValidationCompletedEvent,
    ValidationFailedEvent,
    ValidationPassedEvent,
    ValidationStartedEvent,
)
from app.models.enums import (
    ValidationConcurrencyStrategy,
    ValidationExecutionStatus,
    ValidationResultStatus,
    ValidationSeverity,
    ValidationTriggerType,
    ValidationType,
)
from app.models.validation_check import ValidationCheck
from app.models.validation_execution import ValidationExecution
from app.models.validation_failure import ValidationFailure
from app.models.validation_history import ValidationHistory
from app.models.validation_result import ValidationResult
from app.models.validation_result_detail import ValidationResultDetail
from app.models.validation_rule import ValidationRule
from app.models.validation_score import ValidationScore
from app.models.validation_target import ValidationTarget
from app.repositories.validation_category import ValidationCategoryRepository
from app.repositories.validation_check import ValidationCheckRepository
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_result_detail import ValidationResultDetailRepository
from app.repositories.validation_rule import ValidationRuleRepository
from app.repositories.validation_score import ValidationScoreRepository
from app.repositories.validation_target import ValidationTargetRepository
from app.rules.evaluator import evaluate_rule_chain
from app.scoring.engine import compute_scores

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_ACTIVE_STATUSES = frozenset({ValidationExecutionStatus.QUEUED, ValidationExecutionStatus.RUNNING})
_EXCLUDED_FROM_AGGREGATE = frozenset(
    {ValidationResultStatus.SKIPPED, ValidationResultStatus.NOT_APPLICABLE}
)
_STATUS_PRIORITY = (
    ValidationResultStatus.FAILED,
    ValidationResultStatus.TIMEOUT,
    ValidationResultStatus.WARNING,
    ValidationResultStatus.UNKNOWN,
)
_RESULT_TO_EXECUTION_STATUS = {
    ValidationResultStatus.FAILED: ValidationExecutionStatus.FAILED,
    ValidationResultStatus.TIMEOUT: ValidationExecutionStatus.TIMEOUT,
    ValidationResultStatus.WARNING: ValidationExecutionStatus.WARNING,
    ValidationResultStatus.UNKNOWN: ValidationExecutionStatus.UNKNOWN,
}


def _aggregate_status(results: list[ValidationResult]) -> ValidationExecutionStatus:
    statuses = {r.status for r in results} - _EXCLUDED_FROM_AGGREGATE
    for candidate in _STATUS_PRIORITY:
        if candidate in statuses:
            return _RESULT_TO_EXECUTION_STATUS[candidate]
    return ValidationExecutionStatus.PASSED


@dataclass(frozen=True, slots=True)
class _Collected:
    """The pure-I/O outcome of running one check's own collector against
    one target -- never touches the database, so a batch of these can
    safely be gathered concurrently before
    :meth:`ValidationExecutionService._persist_result` writes each one,
    one at a time.
    """

    check: ValidationCheck
    target: ValidationTarget
    data: dict[str, Any] | None
    error: str | None
    duration_ms: float


class ValidationExecutionService:
    """Creates, runs, and cancels validation executions."""

    def __init__(
        self,
        executions: ValidationExecutionRepository,
        profiles: ValidationProfileRepository,
        checks: ValidationCheckRepository,
        categories: ValidationCategoryRepository,
        rules: ValidationRuleRepository,
        targets: ValidationTargetRepository,
        results: ValidationResultRepository,
        result_details: ValidationResultDetailRepository,
        failures: ValidationFailureRepository,
        scores: ValidationScoreRepository,
        history: ValidationHistoryRepository,
        http_client: httpx.AsyncClient,
        collectors: CollectorRegistry,
        *,
        inventory_base_url: str,
        configuration_base_url: str,
        automation_base_url: str,
        workflow_base_url: str,
        discovery_base_url: str,
        publish_event: EventPublisher,
        max_parallel_checks: int = 10,
    ) -> None:
        self._executions = executions
        self._profiles = profiles
        self._checks = checks
        self._categories = categories
        self._rules = rules
        self._targets = targets
        self._results = results
        self._result_details = result_details
        self._failures = failures
        self._scores = scores
        self._history = history
        self._http_client = http_client
        self._collectors = collectors
        self._inventory_base_url = inventory_base_url
        self._configuration_base_url = configuration_base_url
        self._automation_base_url = automation_base_url
        self._workflow_base_url = workflow_base_url
        self._discovery_base_url = discovery_base_url
        self._publish_event = publish_event
        self._max_parallel_checks = max_parallel_checks

    async def get_by_id(self, execution_id: UUID) -> ValidationExecution:
        """Return the execution identified by *execution_id*.

        Raises:
            NotFoundError: If no such execution exists.
        """
        return await self._executions.require_by_id(execution_id)

    async def list_for_org(
        self, organization_id: UUID, *, status: ValidationExecutionStatus | None = None
    ) -> list[ValidationExecution]:
        """Every execution belonging to *organization_id*, optionally filtered by status."""
        return await self._executions.list_for_org(organization_id, status=status)

    async def get_active_for_profile(self, profile_id: UUID) -> ValidationExecution:
        """Return *profile_id*'s own most recent still-active execution.

        Raises:
            NotFoundError: If no active execution exists for *profile_id*.
        """
        for execution in await self._executions.list_for_profile(profile_id):
            if execution.status in _ACTIVE_STATUSES:
                return execution
        raise NotFoundError(f"Validation profile {profile_id!r} has no active execution.")

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_id: UUID,
        target_ids: list[UUID],
        concurrency_strategy: ValidationConcurrencyStrategy,
        triggered_by: UUID | None,
        trigger_type: ValidationTriggerType = ValidationTriggerType.MANUAL,
    ) -> ValidationExecution:
        """Create a new queued validation execution ("Execute")."""
        return await self._executions.create(
            ValidationExecution(
                organization_id=organization_id,
                project_id=project_id,
                profile_id=profile_id,
                target_ids=[str(target_id) for target_id in target_ids],
                trigger_type=trigger_type,
                concurrency_strategy=concurrency_strategy,
                triggered_by=triggered_by,
            )
        )

    async def cancel(self, execution_id: UUID) -> ValidationExecution:
        """Record caller intent to cancel a queued/running execution ("Cancel").

        Raises:
            NotFoundError: If *execution_id* does not exist.
            ConflictError: If it has already reached a terminal state.
        """
        execution = await self.get_by_id(execution_id)
        if execution.status not in _ACTIVE_STATUSES:
            raise ConflictError(
                f"Validation execution {execution_id!r} is already "
                f"{str(execution.status)!r} and cannot be cancelled."
            )
        execution.status = ValidationExecutionStatus.CANCELLED
        execution.finished_at = datetime.now(UTC)
        return await self._executions.update(execution)

    def _build_context(self, caller_token: str) -> CollectorContext:
        return CollectorContext(
            inventory=InventoryClient(
                self._http_client, base_url=self._inventory_base_url, caller_token=caller_token
            ),
            configuration=ConfigurationClient(
                self._http_client,
                base_url=self._configuration_base_url,
                caller_token=caller_token,
            ),
            automation=AutomationClient(
                self._http_client, base_url=self._automation_base_url, caller_token=caller_token
            ),
            workflow=WorkflowRuntimeClient(
                self._http_client, base_url=self._workflow_base_url, caller_token=caller_token
            ),
            discovery=DiscoveryClient(
                self._http_client, base_url=self._discovery_base_url, caller_token=caller_token
            ),
        )

    async def _collect_one(
        self, check: ValidationCheck, target: ValidationTarget, context: CollectorContext
    ) -> _Collected:
        """Run only *check*'s own collector against *target* -- pure I/O
        against ``context``'s own HTTP clients, no database access at
        all, so it is safe to run many of these concurrently via
        ``asyncio.gather`` (see :meth:`run_execution`'s own docstring
        for why the database-writing half of a check's own result must
        never run this way).
        """
        started = datetime.now(UTC)
        try:
            collected_data = await self._collectors.collect(check, target, context)
        except (DependencyError, ValidationError) as exc:
            duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
            return _Collected(check, target, None, str(exc), duration_ms)
        duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        return _Collected(check, target, collected_data, None, duration_ms)

    async def _persist_result(
        self, execution: ValidationExecution, collected: _Collected
    ) -> ValidationResult:
        """Evaluate *collected*'s own rules (if it collected successfully)
        and persist the resulting :class:`ValidationResult` (plus any
        detail/failure rows) -- always called sequentially, one at a
        time, against this service's own single injected
        ``AsyncSession``.
        """
        check, target = collected.check, collected.target
        if collected.error is not None:
            return await self._results.create(
                ValidationResult(
                    organization_id=execution.organization_id,
                    execution_id=execution.id,
                    target_id=target.id,
                    check_id=check.id,
                    check_type=check.check_type,
                    status=ValidationResultStatus.UNKNOWN,
                    message=collected.error,
                    evaluated_at=datetime.now(UTC),
                    duration_ms=collected.duration_ms,
                )
            )

        collected_data = collected.data or {}
        rules = await self._rules.list_for_check(check.id)
        status, matched_rule = evaluate_rule_chain(rules, collected_data)

        result = await self._results.create(
            ValidationResult(
                organization_id=execution.organization_id,
                execution_id=execution.id,
                target_id=target.id,
                check_id=check.id,
                check_type=check.check_type,
                rule_id=matched_rule.id if matched_rule is not None else None,
                status=status,
                message=matched_rule.description if matched_rule is not None else None,
                evaluated_at=datetime.now(UTC),
                duration_ms=collected.duration_ms,
            )
        )
        for key, value in collected_data.items():
            await self._result_details.create(
                ValidationResultDetail(
                    organization_id=execution.organization_id,
                    result_id=result.id,
                    key=key,
                    value=value,
                )
            )
        if status == ValidationResultStatus.FAILED:
            severity = (
                matched_rule.severity if matched_rule is not None else ValidationSeverity.MEDIUM
            )
            reason = (
                matched_rule.description or matched_rule.name
                if matched_rule is not None
                else f"Check {check.name!r} failed with no matching rule."
            )
            await self._failures.create(
                ValidationFailure(
                    organization_id=execution.organization_id,
                    result_id=result.id,
                    severity=severity,
                    reason=str(reason),
                )
            )
        return result

    async def _is_cancelled(self, execution_id: UUID) -> bool:
        execution = await self._executions.require_by_id(execution_id)
        return execution.status == ValidationExecutionStatus.CANCELLED

    async def run_execution(self, execution_id: UUID, *, caller_token: str) -> ValidationExecution:
        """Run a queued execution to completion ("Sequential Checks"/
        "Parallel Checks").

        ``AsyncSession`` is not safe for genuinely concurrent use by
        multiple asyncio tasks -- even read-only calls can corrupt its
        internal unit-of-work state if two coroutines are interleaved on
        it. ``PARALLEL``/``DISTRIBUTED`` therefore only ever run the
        *collection* phase (:meth:`_collect_one`, pure I/O against
        ``context``'s own HTTP clients, never touching this service's
        own database session) concurrently via ``asyncio.gather``; every
        database write (:meth:`_persist_result`) always happens
        afterward, one at a time, in a plain sequential loop, regardless
        of ``concurrency_strategy``.

        Raises:
            NotFoundError: If *execution_id* does not exist.
        """
        execution = await self.get_by_id(execution_id)
        profile = await self._profiles.require_by_id(execution.profile_id)
        checks = await self._checks.list_by_ids([UUID(c) for c in profile.check_ids])
        targets = await self._targets.list_by_ids([UUID(t) for t in execution.target_ids])

        execution.status = ValidationExecutionStatus.RUNNING
        execution.started_at = datetime.now(UTC)
        execution = await self._executions.update(execution)
        await self._publish_event(
            ValidationStartedEvent(
                source_service="validation-service",
                payload={"execution_id": str(execution.id), "profile_id": str(profile.id)},
            )
        )

        context = self._build_context(caller_token)
        pairs = [(check, target) for check in checks for target in targets]
        results: list[ValidationResult] = []

        if execution.concurrency_strategy == ValidationConcurrencyStrategy.SEQUENTIAL:
            for check, target in pairs:
                if await self._is_cancelled(execution.id):
                    break
                collected = await self._collect_one(check, target, context)
                results.append(await self._persist_result(execution, collected))
        elif not await self._is_cancelled(execution.id):
            semaphore = asyncio.Semaphore(self._max_parallel_checks)

            async def _bounded(check: ValidationCheck, target: ValidationTarget) -> _Collected:
                async with semaphore:
                    return await self._collect_one(check, target, context)

            collected_batch = await asyncio.gather(*(_bounded(c, t) for c, t in pairs))
            if not await self._is_cancelled(execution.id):
                for collected in collected_batch:
                    results.append(await self._persist_result(execution, collected))

        execution = await self.get_by_id(execution.id)
        if execution.status != ValidationExecutionStatus.CANCELLED:
            execution.status = _aggregate_status(results)
        execution.finished_at = datetime.now(UTC)
        execution = await self._executions.update(execution)

        if execution.status != ValidationExecutionStatus.CANCELLED:
            await self._finalize_score(execution, results)

        if execution.status == ValidationExecutionStatus.CANCELLED:
            await self._publish_event(
                ValidationCancelledEvent(
                    source_service="validation-service",
                    payload={"execution_id": str(execution.id)},
                )
            )
        elif execution.status == ValidationExecutionStatus.PASSED:
            await self._publish_event(
                ValidationPassedEvent(
                    source_service="validation-service",
                    payload={"execution_id": str(execution.id)},
                )
            )
        else:
            await self._publish_event(
                ValidationFailedEvent(
                    source_service="validation-service",
                    payload={"execution_id": str(execution.id), "status": str(execution.status)},
                )
            )
        await self._publish_event(
            ValidationCompletedEvent(
                source_service="validation-service",
                payload={"execution_id": str(execution.id), "status": str(execution.status)},
            )
        )
        return execution

    async def _finalize_score(
        self, execution: ValidationExecution, results: list[ValidationResult]
    ) -> None:
        rules_by_id: dict[str, ValidationRule] = {}
        for result in results:
            if result.rule_id is not None:
                rule = await self._rules.get_by_id(result.rule_id)
                if rule is not None:
                    rules_by_id[str(result.rule_id)] = rule

        validation_types_by_check: dict[str, ValidationType] = {}
        for check_id in {result.check_id for result in results}:
            check = await self._checks.get_by_id(check_id)
            if check is None or check.category_id is None:
                continue
            category = await self._categories.get_by_id(check.category_id)
            if category is not None:
                validation_types_by_check[str(check_id)] = category.validation_type

        scores = compute_scores(results, rules_by_id, validation_types_by_check)
        score_row = await self._scores.create(
            ValidationScore(
                organization_id=execution.organization_id,
                execution_id=execution.id,
                overall_score=scores["overall_score"] or 0.0,
                infrastructure_score=scores["infrastructure_score"],
                security_score=scores["security_score"],
                compliance_score=scores["compliance_score"],
                configuration_score=scores["configuration_score"],
                performance_score=scores["performance_score"],
                health_score=scores["health_score"],
                computed_at=datetime.now(UTC),
            )
        )

        for target_id in {r.target_id for r in results}:
            await self._history.create(
                ValidationHistory(
                    organization_id=execution.organization_id,
                    target_id=target_id,
                    execution_id=execution.id,
                    status=execution.status,
                    score=score_row.overall_score,
                    recorded_at=datetime.now(UTC),
                )
            )


__all__ = ["EventPublisher", "ValidationExecutionService"]
