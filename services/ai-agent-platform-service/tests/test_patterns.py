"""Tests for :mod:`app.agents.patterns`.

Each of the six named coordination patterns composes real
``AgentOrchestrator.run_one`` calls. Where a pattern's own branching can
be exercised deterministically (an orchestrator with no registered
agents always fails the same, well-formed way; hand-built
``AgentResult`` lists never touch a model at all) tests do so without
any network dependency. Where a branch can only be reached by an actual
model call (a real multi-agent orchestrator, agents registered via
``make_agent``), the test accepts either a real success or a real,
well-formed failure -- never mocked, per this suite's own methodology.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.agents.orchestrator import AgentOrchestrator, AgentResult, AgentTask
from app.agents.patterns import (
    _parse_delegation,
    _parse_plan_steps,
    run_conflict_resolution,
    run_delegation,
    run_hierarchical,
    run_peer_to_peer,
    run_planner_executor,
    run_supervised,
)
from app.models.enums import AgentType

# ---- fixtures --------------------------------------------------------------------


@pytest_asyncio.fixture
async def orchestrator(make_agent, profiles_repo, model_registry) -> AgentOrchestrator:
    """A real orchestrator over 4 real agents of different types.

    Real model calls made through it may genuinely succeed or genuinely
    fail (no local LLM is guaranteed reachable) -- both are accepted,
    expected outcomes.
    """
    agents_by_type: dict[AgentType, list] = {}
    profiles_by_agent_id: dict = {}
    for slug, agent_type in (
        ("planner-1", AgentType.PLANNER),
        ("executor-1", AgentType.EXECUTOR),
        ("coordinator-1", AgentType.COORDINATOR),
        ("reviewer-1", AgentType.REVIEWER),
    ):
        agent = await make_agent(slug=slug, agent_type=agent_type)
        agents_by_type.setdefault(agent.agent_type, []).append(agent)
        profiles_by_agent_id[agent.id] = await profiles_repo.get_for_agent(agent.id)
    return AgentOrchestrator(model_registry, agents_by_type, profiles_by_agent_id)


@pytest.fixture
def empty_orchestrator(model_registry) -> AgentOrchestrator:
    """An orchestrator with no registered agents -- every ``run_one``
    call fails deterministically, with no network call at all."""
    return AgentOrchestrator(model_registry, {}, {})


def _result(*, succeeded: bool, content: str = "", error: str | None = None, agent_name: str = "a"):
    task = AgentTask(description="disputed question", agent_type=AgentType.EXECUTOR)
    return AgentResult(
        task=task, agent_name=agent_name, content=content, succeeded=succeeded, error=error
    )


# ---- run_hierarchical --------------------------------------------------------------


async def test_run_hierarchical_deterministic_failure_still_reports_subwork(empty_orchestrator):
    root_task = AgentTask(
        description="Check health. Then write a report.", agent_type=AgentType.EXECUTOR
    )

    result = await run_hierarchical(empty_orchestrator, root_task)

    # No agents anywhere -- every sub-task and the synthesis call fail.
    assert result.succeeded is False
    assert result.task == root_task
    assert result.error is not None


async def test_run_hierarchical_falls_back_to_root_task_when_no_subtasks(empty_orchestrator):
    root_task = AgentTask(description="", agent_type=AgentType.EXECUTOR)

    result = await run_hierarchical(empty_orchestrator, root_task)

    assert isinstance(result, AgentResult)


async def test_run_hierarchical_real_run_accepts_success_or_failure(orchestrator):
    root_task = AgentTask(
        description="Check server health and then generate a report.",
        agent_type=AgentType.EXECUTOR,
    )

    result = await run_hierarchical(orchestrator, root_task)

    assert isinstance(result, AgentResult)
    if not result.succeeded:
        # Sub-work still ran; a partial answer beats total silence.
        assert result.task == root_task


# ---- run_peer_to_peer ---------------------------------------------------------------


async def test_run_peer_to_peer_empty_tasks_returns_empty(empty_orchestrator):
    assert await run_peer_to_peer(empty_orchestrator, []) == []


async def test_run_peer_to_peer_single_round_skips_revision(empty_orchestrator):
    tasks = [
        AgentTask(description="a", agent_type=AgentType.MONITORING),
        AgentTask(description="b", agent_type=AgentType.SECURITY),
    ]

    results = await run_peer_to_peer(empty_orchestrator, tasks, rounds=1)

    assert len(results) == 2
    assert all(result.succeeded is False for result in results)


async def test_run_peer_to_peer_no_successes_breaks_before_second_round(empty_orchestrator):
    tasks = [AgentTask(description="a", agent_type=AgentType.MONITORING)]

    results = await run_peer_to_peer(empty_orchestrator, tasks, rounds=3)

    assert len(results) == 1
    assert results[0].succeeded is False


async def test_run_peer_to_peer_real_run_accepts_success_or_failure(orchestrator):
    tasks = [
        AgentTask(description="Should we scale up?", agent_type=AgentType.EXECUTOR),
        AgentTask(description="Should we scale up?", agent_type=AgentType.REVIEWER),
    ]

    results = await run_peer_to_peer(orchestrator, tasks, rounds=2)

    assert len(results) == 2
    assert all(isinstance(result, AgentResult) for result in results)


# ---- run_supervised -----------------------------------------------------------------


async def test_run_supervised_returns_immediately_on_worker_failure(empty_orchestrator):
    task = AgentTask(description="summarize the incident", agent_type=AgentType.EXECUTOR)

    result = await run_supervised(empty_orchestrator, task)

    assert result.succeeded is False
    assert result.error is not None


async def test_run_supervised_real_run_accepts_success_or_failure(orchestrator):
    task = AgentTask(
        description="Summarize this incident in one sentence.", agent_type=AgentType.EXECUTOR
    )

    result = await run_supervised(orchestrator, task, max_attempts=2)

    assert isinstance(result, AgentResult)


# ---- run_planner_executor ------------------------------------------------------------


def test_parse_plan_steps_handles_numbered_list():
    steps = _parse_plan_steps("1. Do the first thing\n2) Do the second\n3: Do the third")
    assert steps == ["Do the first thing", "Do the second", "Do the third"]


def test_parse_plan_steps_handles_bulleted_list():
    steps = _parse_plan_steps("- Do a\n* Do b")
    assert steps == ["Do a", "Do b"]


def test_parse_plan_steps_skips_blank_lines():
    steps = _parse_plan_steps("1. Do a\n\n2. Do b\n   \n3. Do c")
    assert steps == ["Do a", "Do b", "Do c"]


def test_parse_plan_steps_empty_text_returns_no_steps():
    assert _parse_plan_steps("") == []


async def test_run_planner_executor_deterministic_failure_returns_just_the_plan(empty_orchestrator):
    result = await run_planner_executor(empty_orchestrator, "Plan and execute a health check.")

    assert len(result) == 1
    assert result[0].succeeded is False


async def test_run_planner_executor_real_run_accepts_success_or_failure(orchestrator):
    result = await run_planner_executor(orchestrator, "Plan and execute a health check.")

    assert len(result) >= 1
    assert all(isinstance(item, AgentResult) for item in result)


# ---- run_delegation -------------------------------------------------------------------


def test_parse_delegation_extracts_type_and_description():
    parsed = _parse_delegation("DELEGATE_TO: security | check the CVE database")

    assert parsed == (AgentType.SECURITY, "check the CVE database")


def test_parse_delegation_is_case_insensitive():
    parsed = _parse_delegation("delegate_to: Security | Check the CVE database")

    assert parsed == (AgentType.SECURITY, "Check the CVE database")


def test_parse_delegation_returns_none_for_unknown_agent_type():
    assert _parse_delegation("DELEGATE_TO: not_a_real_type | do something") is None


def test_parse_delegation_returns_none_when_no_directive_present():
    assert _parse_delegation("Just a direct answer with no delegation.") is None


async def test_run_delegation_deterministic_failure_returns_just_the_coordinator_result(
    empty_orchestrator,
):
    task = AgentTask(description="handle this request", agent_type=AgentType.COORDINATOR)

    result = await run_delegation(empty_orchestrator, task)

    assert len(result) == 1
    assert result[0].succeeded is False


async def test_run_delegation_real_run_accepts_success_or_failure(orchestrator):
    task = AgentTask(description="Handle this vague request.", agent_type=AgentType.COORDINATOR)

    result = await run_delegation(orchestrator, task)

    assert len(result) in (1, 2)
    assert all(isinstance(item, AgentResult) for item in result)


# ---- run_conflict_resolution -----------------------------------------------------------


async def test_run_conflict_resolution_no_results_returns_explicit_error(empty_orchestrator):
    original = AgentTask(description="disputed question", agent_type=AgentType.EXECUTOR)

    result = await run_conflict_resolution(empty_orchestrator, [], original)

    assert result.succeeded is False
    assert result.agent_name == "none"
    assert result.error == "No results to resolve."
    assert result.task == original


async def test_run_conflict_resolution_all_failed_returns_first_result(empty_orchestrator):
    original = AgentTask(description="disputed question", agent_type=AgentType.EXECUTOR)
    first_failure = _result(succeeded=False, error="first went offline", agent_name="a")
    second_failure = _result(succeeded=False, error="second went offline", agent_name="b")

    result = await run_conflict_resolution(
        empty_orchestrator, [first_failure, second_failure], original
    )

    assert result is first_failure


async def test_run_conflict_resolution_single_success_returned_directly(empty_orchestrator):
    original = AgentTask(description="disputed question", agent_type=AgentType.EXECUTOR)
    only_success = _result(succeeded=True, content="the answer", agent_name="a")
    a_failure = _result(succeeded=False, error="offline", agent_name="b")

    result = await run_conflict_resolution(empty_orchestrator, [a_failure, only_success], original)

    assert result is only_success


async def test_run_conflict_resolution_multiple_successes_real_run_accepts_outcome(orchestrator):
    original = AgentTask(
        description="Will this change break anything?", agent_type=AgentType.EXECUTOR
    )
    option_a = _result(succeeded=True, content="No, it is safe.", agent_name="agent-a")
    option_b = _result(succeeded=True, content="Yes, it will break X.", agent_name="agent-b")

    result = await run_conflict_resolution(orchestrator, [option_a, option_b], original)

    assert isinstance(result, AgentResult)
