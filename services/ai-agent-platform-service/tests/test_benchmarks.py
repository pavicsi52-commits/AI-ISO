"""Tests for :mod:`app.benchmarks.runner` and :mod:`app.benchmarks.service`.

Every benchmark here runs through the *real* :class:`~app.agents
.orchestrator.AgentOrchestrator`, against real ``agents``/
``agent_profiles`` rows seeded by ``make_agent``, and persists real
``agent_benchmarks`` rows -- nothing is mocked.

Three genuinely real model backends drive the three outcomes a
benchmark run can have:

- :class:`~tests.test_evaluation.LocalModelServer` -- a real
  ``http.server`` speaking Ollama's own ``POST /api/chat``, so a case's
  *content* is deterministic and its lexical score can be asserted
  exactly. Reused from ``tests/test_evaluation.py`` rather than
  duplicated.
- :data:`UNREACHABLE_BASE_URL` -- a real dead loopback port, for a
  deterministic per-case failure (``AgentOrchestrator.run_one`` catches
  ``AIError`` and reports it as a failed case, so the *suite* still
  completes).
- the conftest ``model_registry`` -- the real shared registry, whose
  real outcome in an environment with no model daemon is a real
  ``AIError``; the end-to-end test asserts what holds either way.

``BenchmarkStatus.FAILED`` needs the suite itself to raise, which
``run_one`` never does for a provider failure. The real thing that does
raise is a profile whose persisted ``model_provider`` is not a value
this build's own ``ModelProvider`` knows -- ``dispatch_chat`` coerces
that string back to the enum and a stale/unsupported value raises
``ValueError`` straight out of the suite.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.agents.orchestrator import AgentOrchestrator, AgentTask, SharedMemory
from app.benchmarks.runner import (
    DEFAULT_PASS_THRESHOLD,
    BenchmarkCase,
    BenchmarkCaseResult,
    run_benchmark_case,
    run_benchmark_suite,
)
from app.benchmarks.service import BenchmarkService
from app.clients.ollama_client import OllamaClient
from app.clients.registry import ModelRegistry
from app.models.enums import AgentType, BenchmarkStatus, ModelProvider
from app.repositories.benchmark import AgentBenchmarkRepository
from tests.conftest import utcnow
from tests.test_evaluation import UNREACHABLE_BASE_URL, LocalModelServer

UNSUPPORTED_PROVIDER = "retired-vendor"
"""A provider value persisted by an older build that this one dropped."""


@pytest.fixture
def model_server() -> Iterator[LocalModelServer]:
    server = LocalModelServer()
    try:
        yield server
    finally:
        server.close()


def unreachable_registry(http_client: httpx.AsyncClient) -> ModelRegistry:
    """A real registry whose only provider is a dead loopback port."""
    return ModelRegistry(
        {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=UNREACHABLE_BASE_URL)},
        default_provider=ModelProvider.OLLAMA,
        default_model="llama3",
    )


async def orchestrator_for(
    registry: ModelRegistry,
    make_agent: Any,
    profiles_repo: Any,
    *,
    slug: str,
    agent_type: AgentType = AgentType.EXECUTOR,
    profile: dict[str, Any] | None = None,
) -> tuple[Any, AgentOrchestrator]:
    """A real agent plus an orchestrator that can actually resolve it."""
    agent = await make_agent(slug=slug, agent_type=agent_type, profile=profile or {})
    agent_profile = await profiles_repo.get_for_agent(agent.id)
    return agent, AgentOrchestrator(registry, {agent_type: [agent]}, {agent.id: agent_profile})


# ---- BenchmarkCase / BenchmarkCaseResult ---------------------------------------


def test_benchmark_case_defaults_to_no_expected_output():
    case = BenchmarkCase(name="smoke", request="Say hello.")

    assert case.expected_output is None


def test_benchmark_case_is_frozen():
    case = BenchmarkCase(name="smoke", request="Say hello.")

    with pytest.raises(AttributeError):
        case.request = "changed"  # type: ignore[misc]


def test_benchmark_case_result_defaults_to_no_error():
    result = BenchmarkCaseResult(name="smoke", passed=True, score=1.0, content="hi")

    assert result.error is None


def test_benchmark_case_result_to_dict_renders_every_field():
    result = BenchmarkCaseResult(name="smoke", passed=True, score=0.75, content="hi")

    assert result.to_dict() == {
        "name": "smoke",
        "passed": True,
        "score": 0.75,
        "content": "hi",
        "error": None,
    }


def test_benchmark_case_result_to_dict_keeps_the_failure_reason():
    result = BenchmarkCaseResult(
        name="smoke", passed=False, score=0.0, content="", error="provider unreachable"
    )

    assert result.to_dict() == {
        "name": "smoke",
        "passed": False,
        "score": 0.0,
        "content": "",
        "error": "provider unreachable",
    }


def test_default_pass_threshold_is_seven_tenths():
    assert DEFAULT_PASS_THRESHOLD == 0.7


# ---- run_benchmark_case() -------------------------------------------------------


async def test_run_benchmark_case_fails_when_no_agent_can_be_resolved(
    model_registry: ModelRegistry,
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    case = BenchmarkCase(name="unroutable", request="Say hello.", expected_output="hello")

    result = await run_benchmark_case(orchestrator, AgentType.RESEARCHER, case)

    assert result.name == "unroutable"
    assert result.passed is False
    assert result.score == 0.0
    assert result.content == ""
    assert result.error == "No agent registered for researcher and no executor agent."


async def test_run_benchmark_case_fails_when_the_provider_is_unreachable(
    http_client: httpx.AsyncClient, make_agent, profiles_repo
):
    _agent, orchestrator = await orchestrator_for(
        unreachable_registry(http_client), make_agent, profiles_repo, slug="offline-bench"
    )
    case = BenchmarkCase(name="offline", request="Say hello.", expected_output="hello")

    result = await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case)

    assert result.passed is False
    assert result.score == 0.0
    assert result.content == ""
    assert "Every model provider in the fallback chain failed" in (result.error or "")


async def test_run_benchmark_case_scores_an_exact_answer_full_marks(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    model_server.queue_reply("the quick brown fox")
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="exact-bench"
    )
    case = BenchmarkCase(
        name="exact", request="Name the animal.", expected_output="the quick brown fox"
    )

    result = await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case)

    assert result.passed is True
    assert result.score == 1.0
    assert result.content == "the quick brown fox"
    assert result.error is None
    assert model_server.prompts == ["Name the animal."]


async def test_run_benchmark_case_without_expected_output_passes_on_any_answer(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    model_server.queue_reply("something entirely unrelated")
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="open-bench"
    )
    case = BenchmarkCase(name="open", request="Say anything.")

    result = await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case)

    assert result.score == 1.0
    assert result.passed is True
    assert result.content == "something entirely unrelated"


async def test_run_benchmark_case_scores_a_partial_answer_below_the_threshold(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    model_server.queue_reply("the cat sat")
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="partial-bench"
    )
    case = BenchmarkCase(
        name="partial", request="What did the cat do?", expected_output="the cat ran"
    )

    result = await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case)

    assert result.score == 0.5
    assert result.passed is False
    assert result.error is None


async def test_run_benchmark_case_passes_a_score_exactly_on_the_threshold(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    model_server.queue_reply("the cat sat")
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="boundary-bench"
    )
    case = BenchmarkCase(
        name="boundary", request="What did the cat do?", expected_output="the cat ran"
    )

    result = await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case, pass_threshold=0.5)

    assert result.score == 0.5
    assert result.passed is True


async def test_run_benchmark_case_with_a_zero_threshold_passes_a_zero_score(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    model_server.queue_reply("gamma delta")
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="zero-threshold"
    )
    case = BenchmarkCase(name="zero", request="Name two letters.", expected_output="alpha beta")

    result = await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case, pass_threshold=0.0)

    assert result.score == 0.0
    assert result.passed is True


async def test_run_benchmark_case_falls_back_to_the_executor_agent(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    # No reviewer agent exists, but the orchestrator's own executor
    # fallback resolves one, so the case still runs for real.
    model_server.queue_reply("looks good")
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="fallback-bench"
    )
    case = BenchmarkCase(name="review", request="Review this change.")

    result = await run_benchmark_case(orchestrator, AgentType.REVIEWER, case)

    assert result.passed is True
    assert result.content == "looks good"


async def test_run_benchmark_case_propagates_an_unsupported_persisted_provider(
    model_registry: ModelRegistry, make_agent, profiles_repo
):
    # Not an AIError, so ``run_one`` does not absorb it: this is the
    # class of failure that makes a whole suite unrunnable.
    _agent, orchestrator = await orchestrator_for(
        model_registry,
        make_agent,
        profiles_repo,
        slug="stale-provider-case",
        profile={"model_provider": UNSUPPORTED_PROVIDER},
    )
    case = BenchmarkCase(name="broken", request="Say hello.")

    with pytest.raises(ValueError, match=UNSUPPORTED_PROVIDER):
        await run_benchmark_case(orchestrator, AgentType.EXECUTOR, case)


# ---- run_benchmark_suite() ------------------------------------------------------


async def test_run_benchmark_suite_with_no_cases_returns_no_results(
    model_registry: ModelRegistry,
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})

    assert await run_benchmark_suite(orchestrator, AgentType.EXECUTOR, []) == []


async def test_run_benchmark_suite_runs_every_case_in_order(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    for reply in ("the quick brown fox", "the cat sat", "gamma delta"):
        model_server.queue_reply(reply)
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="suite-order"
    )
    cases = [
        BenchmarkCase(name="a", request="Name the animal.", expected_output="the quick brown fox"),
        BenchmarkCase(name="b", request="What did the cat do?", expected_output="the cat ran"),
        BenchmarkCase(name="c", request="Name two letters.", expected_output="alpha beta"),
    ]

    results = await run_benchmark_suite(orchestrator, AgentType.EXECUTOR, cases)

    assert [result.name for result in results] == ["a", "b", "c"]
    assert [result.score for result in results] == [1.0, 0.5, 0.0]
    assert [result.passed for result in results] == [True, False, False]
    assert model_server.prompts == [
        "Name the animal.",
        "What did the cat do?",
        "Name two letters.",
    ]


async def test_run_benchmark_suite_applies_the_threshold_to_every_case(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    for reply in ("the cat sat", "the cat sat"):
        model_server.queue_reply(reply)
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="suite-threshold"
    )
    cases = [
        BenchmarkCase(name="a", request="First?", expected_output="the cat ran"),
        BenchmarkCase(name="b", request="Second?", expected_output="the cat ran"),
    ]

    lenient = await run_benchmark_suite(
        orchestrator, AgentType.EXECUTOR, cases[:1], pass_threshold=0.5
    )
    strict = await run_benchmark_suite(
        orchestrator, AgentType.EXECUTOR, cases[1:], pass_threshold=0.51
    )

    assert lenient[0].passed is True
    assert strict[0].passed is False


async def test_run_benchmark_suite_reports_each_failure_without_aborting(
    http_client: httpx.AsyncClient, make_agent, profiles_repo
):
    _agent, orchestrator = await orchestrator_for(
        unreachable_registry(http_client), make_agent, profiles_repo, slug="suite-offline"
    )
    cases = [BenchmarkCase(name="a", request="First?"), BenchmarkCase(name="b", request="Second?")]

    results = await run_benchmark_suite(orchestrator, AgentType.EXECUTOR, cases)

    assert [result.name for result in results] == ["a", "b"]
    assert all(result.passed is False for result in results)
    assert all("fallback chain failed" in (result.error or "") for result in results)


async def test_run_benchmark_suite_propagates_a_suite_breaking_error(
    model_registry: ModelRegistry, make_agent, profiles_repo
):
    _agent, orchestrator = await orchestrator_for(
        model_registry,
        make_agent,
        profiles_repo,
        slug="stale-provider-suite",
        profile={"model_provider": UNSUPPORTED_PROVIDER},
    )

    with pytest.raises(ValueError, match=UNSUPPORTED_PROVIDER):
        await run_benchmark_suite(
            orchestrator, AgentType.EXECUTOR, [BenchmarkCase(name="a", request="Say hello.")]
        )


# ---- BenchmarkService.run() -----------------------------------------------------


CASES = [
    BenchmarkCase(name="exact", request="Name the animal.", expected_output="the quick brown fox"),
    BenchmarkCase(name="partial", request="What did the cat do?", expected_output="the cat ran"),
    BenchmarkCase(name="wrong", request="Name two letters.", expected_output="alpha beta"),
]
REPLIES = ("the quick brown fox", "the cat sat", "gamma delta")


async def test_run_records_a_completed_suite_with_its_rolled_up_counts(
    benchmarks_repo: AgentBenchmarkRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    make_agent,
    profiles_repo,
    organization_id,
):
    for reply in REPLIES:
        model_server.queue_reply(reply)
    agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="rollup-bench"
    )
    before = utcnow()

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="nightly-regression",
        cases=CASES,
        triggered_by="scheduler",
    )

    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.name == "nightly-regression"
    assert benchmark.organization_id == organization_id
    assert benchmark.agent_id == agent.id
    assert benchmark.total_cases == 3
    assert benchmark.passed_cases == 1
    assert benchmark.failed_cases == 2
    assert benchmark.score == 0.5
    assert benchmark.triggered_by == "scheduler"
    assert benchmark.error is None
    assert before <= benchmark.started_at <= benchmark.completed_at <= utcnow()


async def test_run_records_every_case_result_in_order(
    benchmarks_repo: AgentBenchmarkRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    make_agent,
    profiles_repo,
    organization_id,
):
    for reply in REPLIES:
        model_server.queue_reply(reply)
    agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="results-bench"
    )

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="results",
        cases=CASES,
    )

    assert benchmark.results == [
        {
            "name": "exact",
            "passed": True,
            "score": 1.0,
            "content": "the quick brown fox",
            "error": None,
        },
        {"name": "partial", "passed": False, "score": 0.5, "content": "the cat sat", "error": None},
        {"name": "wrong", "passed": False, "score": 0.0, "content": "gamma delta", "error": None},
    ]


async def test_run_with_no_cases_completes_with_a_zero_score(
    benchmarks_repo: AgentBenchmarkRepository,
    model_registry: ModelRegistry,
    make_agent,
    profiles_repo,
    organization_id,
):
    agent, orchestrator = await orchestrator_for(
        model_registry, make_agent, profiles_repo, slug="empty-suite"
    )

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="empty",
        cases=[],
    )

    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.total_cases == 0
    assert benchmark.passed_cases == 0
    assert benchmark.failed_cases == 0
    assert benchmark.score == 0.0
    assert benchmark.results == []


async def test_run_completes_even_when_every_case_failed(
    benchmarks_repo: AgentBenchmarkRepository,
    http_client: httpx.AsyncClient,
    make_agent,
    profiles_repo,
    organization_id,
):
    # Per this method's own docstring: case pass/fail is an expected
    # outcome of a run that completed, never a run failure.
    agent, orchestrator = await orchestrator_for(
        unreachable_registry(http_client), make_agent, profiles_repo, slug="all-failed-bench"
    )

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="all-failed",
        cases=CASES,
    )

    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.passed_cases == 0
    assert benchmark.failed_cases == 3
    assert benchmark.score == 0.0
    assert benchmark.error is None
    assert all("fallback chain failed" in str(result["error"]) for result in benchmark.results)


async def test_run_completes_when_no_agent_of_that_type_is_registered(
    benchmarks_repo: AgentBenchmarkRepository,
    model_registry: ModelRegistry,
    make_agent,
    organization_id,
):
    # ``AgentOrchestrator.run_one`` never raises for an unresolvable
    # agent -- it reports a failed case -- so the *suite* still completes
    # and only the case counts record the outcome.
    agent = await make_agent(slug="unregistered-bench")
    orchestrator = AgentOrchestrator(model_registry, {}, {})

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.VALIDATOR,
        name="unroutable",
        cases=CASES,
    )

    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.total_cases == 3
    assert benchmark.passed_cases == 0
    assert benchmark.failed_cases == 3
    assert benchmark.score == 0.0
    assert all(
        result["error"] == "No agent registered for validator and no executor agent."
        for result in benchmark.results
    )


async def test_run_records_a_failed_suite_when_the_suite_itself_cannot_run(
    benchmarks_repo: AgentBenchmarkRepository,
    model_registry: ModelRegistry,
    make_agent,
    profiles_repo,
    organization_id,
):
    agent, orchestrator = await orchestrator_for(
        model_registry,
        make_agent,
        profiles_repo,
        slug="stale-provider-bench",
        profile={"model_provider": UNSUPPORTED_PROVIDER},
    )
    before = utcnow()

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="unrunnable",
        cases=CASES,
        triggered_by="scheduler",
    )

    assert benchmark.status == BenchmarkStatus.FAILED
    assert UNSUPPORTED_PROVIDER in (benchmark.error or "")
    assert benchmark.total_cases == 3
    assert benchmark.passed_cases == 0
    assert benchmark.failed_cases == 0
    assert benchmark.results == []
    assert benchmark.score is None
    assert benchmark.triggered_by == "scheduler"
    assert before <= benchmark.started_at <= benchmark.completed_at <= utcnow()


async def test_run_persists_a_row_whose_status_reloads_as_a_plain_string(
    benchmarks_repo: AgentBenchmarkRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    db_session,
    make_agent,
    profiles_repo,
    organization_id,
):
    for reply in REPLIES:
        model_server.queue_reply(reply)
    agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="persisted-bench"
    )

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="persisted",
        cases=CASES,
    )
    # Read the identities out before expiring: a lazily refreshed
    # attribute on an AsyncSession would be implicit IO outside ``await``.
    benchmark_id, agent_id = benchmark.id, agent.id
    db_session.expire_all()
    reloaded = await benchmarks_repo.get_by_id(benchmark_id)

    assert reloaded is not None
    # This platform's own enum-as-str convention: compare with ``==``.
    assert not isinstance(reloaded.status, BenchmarkStatus)
    assert reloaded.status == BenchmarkStatus.COMPLETED
    assert reloaded.passed_cases == 1
    assert reloaded.failed_cases == 2
    assert reloaded.score == 0.5
    assert [result["name"] for result in reloaded.results] == ["exact", "partial", "wrong"]
    assert [row.id for row in await benchmarks_repo.list_for_agent(agent_id)] == [benchmark_id]


async def test_run_end_to_end_against_the_real_shared_registry(
    benchmarks_repo: AgentBenchmarkRepository,
    model_registry: ModelRegistry,
    make_agent,
    profiles_repo,
    organization_id,
):
    # The real shared registry: with no model daemon running every case
    # genuinely fails, with one running some may pass. Either way the
    # suite completes and its own counts stay internally consistent.
    agent, orchestrator = await orchestrator_for(
        model_registry, make_agent, profiles_repo, slug="real-registry-bench"
    )

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="real-registry",
        cases=CASES,
    )

    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.total_cases == 3
    assert benchmark.passed_cases + benchmark.failed_cases == 3
    assert benchmark.score is not None
    assert 0.0 <= benchmark.score <= 1.0
    assert [result["name"] for result in benchmark.results] == ["exact", "partial", "wrong"]


async def test_run_scopes_the_recorded_benchmark_to_its_own_agent_and_tenant(
    benchmarks_repo: AgentBenchmarkRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    make_agent,
    profiles_repo,
    organization_id,
):
    model_server.queue_reply("the quick brown fox")
    agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="scoped-bench"
    )
    other_agent = await make_agent(slug="other-bench-agent")

    benchmark = await BenchmarkService(benchmarks_repo, orchestrator).run(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_type=AgentType.EXECUTOR,
        name="scoped",
        cases=CASES[:1],
    )

    assert benchmark.agent_id == agent.id
    assert await benchmarks_repo.list_for_agent(other_agent.id) == []
    assert [row.id for row in await benchmarks_repo.list_for_org(organization_id)] == [benchmark.id]
    assert await benchmarks_repo.list_for_org(uuid.uuid4()) == []


async def test_run_uses_the_orchestrator_task_shape_the_runner_documents(
    http_client: httpx.AsyncClient, model_server: LocalModelServer, make_agent, profiles_repo
):
    # A benchmark case is dispatched as a plain AgentTask with a fresh
    # SharedMemory, exactly like any other execution -- so a case never
    # sees another case's findings.
    for reply in ("first answer", "second answer"):
        model_server.queue_reply(reply)
    _agent, orchestrator = await orchestrator_for(
        model_server.registry(http_client), make_agent, profiles_repo, slug="task-shape-bench"
    )

    direct = await orchestrator.run_one(
        AgentTask(description="First?", agent_type=AgentType.EXECUTOR), SharedMemory()
    )
    via_runner = await run_benchmark_case(
        orchestrator, AgentType.EXECUTOR, BenchmarkCase(name="second", request="Second?")
    )

    assert direct.content == "first answer"
    assert via_runner.content == "second answer"
    assert model_server.prompts == ["First?", "Second?"]
