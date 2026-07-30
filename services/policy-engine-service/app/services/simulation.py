"""Simulation as a service: run a rehearsal, store what it found.

The comparison lives in :mod:`app.simulation.engine`, which calls the
same :func:`~app.evaluation.engine.evaluate` a live decision does. This
service loads the two catalogues and records the result.

**Draft policies are included by id, never by status.** A preview that
swept in every draft would answer a question nobody asked -- "what if I
published everything anybody is working on?" -- and would change its
answer whenever a colleague started editing something unrelated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.attributes.resolver import EvaluationContext
from app.evaluation.engine import EvaluablePolicy, policy_from_row
from app.events.policy_events import SOURCE_SERVICE, SimulationCompletedEvent
from app.models.enums import (
    ActionType,
    JobStatus,
    PolicyEffect,
    ResourceType,
    SimulationKind,
    SubjectType,
)
from app.models.governance import PolicySimulation
from app.notifications.policy_notifications import PolicyNotificationService
from app.repositories.policy import PolicyRepository
from app.repositories.runtime import PolicySimulationRepository
from app.simulation import engine as simulation
from app.types import EventPublisher

logger = get_logger("app.services.simulation")


def status_of(record: PolicySimulation) -> JobStatus:
    """A simulation's status as a genuine enum member."""
    value = record.status
    return value if isinstance(value, JobStatus) else JobStatus(value)


def kind_of(record: PolicySimulation) -> SimulationKind:
    """A simulation's kind as a genuine enum member."""
    value = record.kind
    return value if isinstance(value, SimulationKind) else SimulationKind(value)


class SimulationService:
    """Runs and stores policy simulations."""

    def __init__(
        self,
        policies: PolicyRepository,
        simulations: PolicySimulationRepository,
        notifications: PolicyNotificationService,
        *,
        publish_event: EventPublisher,
        max_requests: int = 1_000,
        default_effect: PolicyEffect = PolicyEffect.DENY,
        fail_closed: bool = True,
        max_policies: int = 500,
    ) -> None:
        self._policies = policies
        self._simulations = simulations
        self._notifications = notifications
        self._publish_event = publish_event
        self._max_requests = max_requests
        self._default_effect = default_effect
        self._fail_closed = fail_closed
        self._max_policies = max_policies

    async def run(
        self,
        organization_id: UUID,
        *,
        label: str,
        requests: list[simulation.SimulationRequest],
        kind: SimulationKind = SimulationKind.WHAT_IF,
        draft_policy_ids: list[UUID] | None = None,
        excluded_policy_ids: list[UUID] | None = None,
        notify_user_id: str | None = None,
        actor_id: UUID | None = None,
    ) -> PolicySimulation:
        """Rehearse a set of requests against a candidate catalogue.

        Raises:
            ValidationError: If there are too many requests, or none.
        """
        if not requests:
            raise ValidationError(
                "A simulation needs at least one request to rehearse. Without one it "
                "can only report the conflicts, which /policies/simulate already does."
            )
        if len(requests) > self._max_requests:
            raise ValidationError(
                f"A simulation may rehearse at most {self._max_requests} requests, "
                f"got {len(requests)}. A simulation runs the same engine a live "
                "decision does, so an unbounded one competes with real authorization."
            )

        record = await self._simulations.create(
            PolicySimulation(
                organization_id=organization_id,
                label=label,
                kind=kind,
                status=JobStatus.RUNNING,
                draft_policy_ids=[str(one) for one in draft_policy_ids or []],
                request_count=len(requests),
                started_at=datetime.now(UTC),
                created_by=actor_id,
            )
        )

        try:
            baseline = await self._baseline(organization_id)
            candidate = await self._candidate(
                organization_id,
                baseline,
                draft_policy_ids=draft_policy_ids or [],
                excluded_policy_ids=excluded_policy_ids or [],
            )
            result = simulation.simulate(
                baseline,
                candidate,
                requests,
                default_effect=self._default_effect,
                fail_closed=self._fail_closed,
                max_policies=self._max_policies,
            )

            record.allowed_count = result.allowed_count
            record.denied_count = result.denied_count
            record.changed_count = result.changed_count
            record.conflicts = result.conflicts
            record.results = result.as_dict()
            record.summary = result.summarise()
            record.duration_ms = result.duration_ms
            record.status = JobStatus.SUCCEEDED
        except Exception as exc:
            record.status = JobStatus.FAILED
            record.error = str(exc)
            logger.warning(
                "A policy simulation failed.",
                extra={"extra_fields": {"label": label, "error": str(exc)}},
            )

        record.finished_at = datetime.now(UTC)
        stored = await self._simulations.update(record)

        if status_of(stored) is JobStatus.SUCCEEDED:
            await self._publish_event(
                SimulationCompletedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "simulation_id": str(stored.id),
                        "label": label,
                        "changed_count": stored.changed_count,
                        "conflicts": len(stored.conflicts or []),
                    },
                )
            )
            if notify_user_id:
                await self._notifications.send_simulation_completed(
                    notify_user_id, label=label, summary=stored.summary or ""
                )
        return stored

    async def preview(
        self,
        organization_id: UUID,
        *,
        requests: list[simulation.SimulationRequest],
        draft_policy_ids: list[UUID] | None = None,
        excluded_policy_ids: list[UUID] | None = None,
    ) -> dict[str, Any]:
        """Run a rehearsal without storing it.

        For the interactive case -- somebody adjusting a rule and asking
        again -- where a stored row per keystroke would bury the
        deliberate simulations somebody wants to find later.
        """
        baseline = await self._baseline(organization_id)
        candidate = await self._candidate(
            organization_id,
            baseline,
            draft_policy_ids=draft_policy_ids or [],
            excluded_policy_ids=excluded_policy_ids or [],
        )
        return simulation.impact_of(
            baseline,
            candidate,
            requests,
            default_effect=self._default_effect,
            fail_closed=self._fail_closed,
            max_policies=self._max_policies,
        )

    async def detect_conflicts(self, organization_id: UUID) -> list[dict[str, Any]]:
        """Find contradicting pairs in the live catalogue."""
        return simulation.detect_conflicts(await self._baseline(organization_id))

    async def _baseline(self, organization_id: UUID) -> list[EvaluablePolicy]:
        """The live catalogue: what decisions use right now."""
        rows = await self._policies.list_evaluable(organization_id, limit=self._max_policies)
        return self._loadable(rows)

    async def _candidate(
        self,
        organization_id: UUID,
        baseline: list[EvaluablePolicy],
        *,
        draft_policy_ids: list[UUID],
        excluded_policy_ids: list[UUID],
    ) -> list[EvaluablePolicy]:
        """The catalogue as it would be: live, plus drafts, minus exclusions.

        Exclusions are what makes "what breaks if I retire this policy?"
        answerable -- the mirror image of the more obvious question, and
        the one whose answer people are usually more wrong about.
        """
        excluded = {str(one) for one in excluded_policy_ids}
        candidate = [one for one in baseline if one.policy_id not in excluded]

        if draft_policy_ids:
            drafts = await self._policies.list_by_ids(organization_id, draft_policy_ids)
            known = {one.policy_id for one in candidate}
            for loaded in self._loadable(drafts, is_draft=True):
                if loaded.policy_id not in known:
                    candidate.append(loaded)
        return candidate

    @staticmethod
    def _loadable(rows: list[Any], *, is_draft: bool = False) -> list[EvaluablePolicy]:
        """Rebuild the policies that can be rebuilt, skipping the rest.

        A policy whose stored rule will not parse is skipped and logged.
        In a simulation that is the right call for the same reason it is
        live: one corrupt row must not make the whole preview unavailable,
        and the skip is loud enough to notice.
        """
        loaded: list[EvaluablePolicy] = []
        for row in rows:
            try:
                loaded.append(policy_from_row(row, is_draft=is_draft))
            except Exception as exc:
                logger.error(
                    "A stored policy could not be loaded for simulation and was skipped.",
                    extra={
                        "extra_fields": {
                            "policy_id": str(row.id),
                            "slug": row.slug,
                            "error": str(exc),
                        }
                    },
                )
        return loaded

    async def get(self, organization_id: UUID, simulation_id: UUID) -> PolicySimulation:
        """One stored simulation.

        Raises:
            NotFoundError: If it does not exist in this organization.
        """
        return await self._simulations.require_by_id(organization_id, simulation_id)

    async def list_simulations(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[PolicySimulation]:
        """Stored simulations, most recent first."""
        return await self._simulations.list_for_org(organization_id, limit=limit)


def request_from_payload(payload: dict[str, Any], *, index: int) -> simulation.SimulationRequest:
    """Build one simulation request from an API payload.

    Raises:
        ValidationError: If it names an unknown subject type, resource
            type, or action.
    """
    try:
        return simulation.SimulationRequest(
            label=str(payload.get("label") or f"request-{index}"),
            subject_type=SubjectType(payload["subject_type"]),
            resource_type=ResourceType(payload["resource_type"]),
            action=ActionType(payload["action"]),
            context=EvaluationContext(
                subject=dict(payload.get("subject") or {}),
                resource=dict(payload.get("resource") or {}),
                action=dict(payload.get("action_attributes") or {}),
                context=dict(payload.get("context") or {}),
                environment=dict(payload.get("environment") or {}),
                organization=dict(payload.get("organization") or {}),
                project=dict(payload.get("project") or {}),
                custom=dict(payload.get("custom") or {}),
            ),
        )
    except (KeyError, ValueError) as exc:
        raise ValidationError(f"Simulation request {index} is unusable: {exc}") from exc


__all__ = ["SimulationService", "kind_of", "request_from_payload", "status_of"]
