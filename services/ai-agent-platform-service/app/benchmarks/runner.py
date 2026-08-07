"""Runs a fixed set of benchmark cases against an agent type (docs/060
"EVALUATION" benchmarking; backs :class:`~app.models.benchmark
.AgentBenchmark`).

Reuses :meth:`~app.agents.orchestrator.AgentOrchestrator.run_one`
directly -- a benchmark case is just a task run through the same
dispatch every other execution uses, scored afterward.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.orchestrator import AgentOrchestrator, AgentTask, SharedMemory
from app.evaluation.scoring import score_task_accuracy_lexical
from app.models.enums import AgentType

DEFAULT_PASS_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One fixed input/expected-output pair in a benchmark suite."""

    name: str
    request: str
    expected_output: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    """One case's own outcome."""

    name: str
    passed: bool
    score: float
    content: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "content": self.content,
            "error": self.error,
        }


async def run_benchmark_case(
    orchestrator: AgentOrchestrator,
    agent_type: AgentType,
    case: BenchmarkCase,
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> BenchmarkCaseResult:
    """Run one case and score it.

    A case with no ``expected_output`` passes on a bare successful
    run (score ``1.0``) -- there is nothing to compare against, so
    "did it answer at all" is the only judgement available.
    """
    result = await orchestrator.run_one(
        AgentTask(description=case.request, agent_type=agent_type), SharedMemory()
    )
    if not result.succeeded:
        return BenchmarkCaseResult(
            name=case.name, passed=False, score=0.0, content="", error=result.error
        )

    score = (
        score_task_accuracy_lexical(result.content, case.expected_output)
        if case.expected_output is not None
        else 1.0
    )
    return BenchmarkCaseResult(
        name=case.name, passed=score >= pass_threshold, score=score, content=result.content
    )


async def run_benchmark_suite(
    orchestrator: AgentOrchestrator,
    agent_type: AgentType,
    cases: list[BenchmarkCase],
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> list[BenchmarkCaseResult]:
    """Run every case in sequence.

    Sequential, not parallel: benchmark runs are comparison-sensitive
    (this run's own score against a prior run's), and interleaving
    cases would only save latency at the cost of a shared, harder-to-
    reproduce run order.
    """
    return [
        await run_benchmark_case(orchestrator, agent_type, case, pass_threshold=pass_threshold)
        for case in cases
    ]


__all__ = [
    "DEFAULT_PASS_THRESHOLD",
    "BenchmarkCase",
    "BenchmarkCaseResult",
    "run_benchmark_case",
    "run_benchmark_suite",
]
