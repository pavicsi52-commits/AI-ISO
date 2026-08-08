"""Runs and records one benchmark suite against an agent (docs/060
"EVALUATION" benchmarking).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.agents.orchestrator import AgentOrchestrator
from app.benchmarks.runner import (
    DEFAULT_PASS_THRESHOLD,
    BenchmarkCase,
    run_benchmark_suite,
)
from app.models.benchmark import AgentBenchmark
from app.models.enums import AgentType, BenchmarkStatus
from app.repositories.benchmark import AgentBenchmarkRepository


class BenchmarkService:
    """Runs a fixed benchmark suite and persists the rolled-up result."""

    def __init__(
        self, benchmarks: AgentBenchmarkRepository, orchestrator: AgentOrchestrator
    ) -> None:
        self._benchmarks = benchmarks
        self._orchestrator = orchestrator

    async def run(
        self,
        *,
        organization_id: UUID,
        agent_id: UUID,
        agent_type: AgentType,
        name: str,
        cases: list[BenchmarkCase],
        triggered_by: str | None = None,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    ) -> AgentBenchmark:
        """Run every case in *cases* against *agent_type* and record
        one rolled-up :class:`AgentBenchmark`.

        The benchmark's own ``status`` reflects whether the *suite
        itself* ran to completion, not whether every case passed --
        pass/fail counts are a separate, expected outcome, not a
        run failure. A run only becomes ``FAILED`` if running it raised
        outright (e.g. an agent profile whose persisted
        ``model_provider`` is no longer a value this build's own
        :class:`~app.models.enums.ModelProvider` knows, which
        :func:`~app.clients.dispatch.dispatch_chat` cannot coerce).

        An *unresolvable* ``agent_type`` is **not** such a case:
        :meth:`~app.agents.orchestrator.AgentOrchestrator.run_one`
        never raises, so a suite with no agent registered for it still
        records ``COMPLETED`` with every case failed.
        """
        started_at = datetime.now(UTC)
        try:
            results = await run_benchmark_suite(
                self._orchestrator, agent_type, cases, pass_threshold=pass_threshold
            )
        except Exception as exc:
            return await self._benchmarks.create(
                AgentBenchmark(
                    organization_id=organization_id,
                    agent_id=agent_id,
                    name=name,
                    status=BenchmarkStatus.FAILED,
                    total_cases=len(cases),
                    passed_cases=0,
                    failed_cases=0,
                    results=[],
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    triggered_by=triggered_by,
                    error=str(exc),
                )
            )

        passed_cases = sum(1 for result in results if result.passed)
        overall_score = sum(result.score for result in results) / len(results) if results else 0.0

        return await self._benchmarks.create(
            AgentBenchmark(
                organization_id=organization_id,
                agent_id=agent_id,
                name=name,
                status=BenchmarkStatus.COMPLETED,
                total_cases=len(results),
                passed_cases=passed_cases,
                failed_cases=len(results) - passed_cases,
                score=overall_score,
                results=[result.to_dict() for result in results],
                started_at=started_at,
                completed_at=datetime.now(UTC),
                triggered_by=triggered_by,
            )
        )


__all__ = ["BenchmarkService"]
