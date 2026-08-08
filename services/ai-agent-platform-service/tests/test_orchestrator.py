"""Tests for :mod:`app.agents.orchestrator`.

Covers the pure logic (``route``, ``decompose``, ``select_dynamically``,
``aggregate``, ``SharedMemory``) with no infrastructure, and
``AgentOrchestrator.agent_for``/``run_one``/``run_sequential``/
``run_parallel`` against real agents/profiles seeded through
``make_agent`` and a real (possibly unreachable) ``ModelRegistry`` --
per this suite's own methodology, a real "every provider failed"
failure is an accepted, expected outcome, never mocked away.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.agents.orchestrator import (
    AgentOrchestrator,
    AgentResult,
    AgentTask,
    SharedMemory,
    aggregate,
    decompose,
    route,
    select_dynamically,
)
from app.models.agent import Agent
from app.models.enums import AgentType

# ---- AgentTask / AgentResult --------------------------------------------------


def test_agent_task_defaults_to_empty_context():
    task = AgentTask(description="do the thing", agent_type=AgentType.EXECUTOR)
    assert task.context == ""


def test_agent_result_defaults_zero_tokens_and_no_error():
    result = AgentResult(
        task=AgentTask(description="x", agent_type=AgentType.EXECUTOR),
        agent_name="agent-1",
        content="hello",
        succeeded=True,
    )
    assert result.error is None
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


# ---- SharedMemory --------------------------------------------------------------


def test_shared_memory_as_context_empty_when_no_facts():
    assert SharedMemory().as_context() == ""


def test_shared_memory_records_and_renders_facts_in_order():
    memory = SharedMemory()
    memory.record("step one", "found X")
    memory.record("step two", "found Y")

    rendered = memory.as_context()

    assert rendered == "Findings from earlier steps:\n- step one: found X\n- step two: found Y"


def test_shared_memory_record_overwrites_same_key():
    memory = SharedMemory()
    memory.record("step", "first")
    memory.record("step", "second")

    assert memory.facts == {"step": "second"}


# ---- route() ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        # No "cluster" here: that keyword is INFRASTRUCTURE's and is
        # longer than "cpu", so by route()'s own longest-match rule it
        # would win. See test_route_picks_longest_matching_keyword below.
        ("CPU usage is spiking", AgentType.MONITORING),
        ("please run the nightly automation playbook", AgentType.AUTOMATION),
        ("what is the network topology of this cluster", AgentType.INFRASTRUCTURE),
        ("is this configuration compliant with the standard", AgentType.COMPLIANCE),
        ("check for any credential exposure vulnerability", AgentType.SECURITY),
        ("generate a summary dashboard", AgentType.REPORTING),
        ("how do i restore from a runbook", AgentType.KNOWLEDGE_GRAPH),
        ("please validate this configuration", AgentType.VALIDATOR),
        ("can you review and approve this change", AgentType.REVIEWER),
        ("research and investigate the outage", AgentType.RESEARCHER),
        ("draft a roadmap and strategy", AgentType.PLANNER),
        ("coordinate and delegate this work", AgentType.COORDINATOR),
        ("say hello to the team", AgentType.EXECUTOR),
    ],
)
def test_route_matches_expected_agent_type(description: str, expected: AgentType):
    assert route(description) == expected


def test_route_is_case_insensitive():
    assert route("SECURITY AUDIT REQUIRED") == AgentType.SECURITY


def test_route_picks_longest_matching_keyword():
    # "server" (6 chars, INFRASTRUCTURE) beats "cpu" (3 chars, MONITORING).
    assert route("check the server cpu graph") == AgentType.INFRASTRUCTURE


def test_route_falls_back_to_executor_for_empty_description():
    assert route("") == AgentType.EXECUTOR


# ---- decompose() -------------------------------------------------------------------


def test_decompose_empty_request_returns_no_tasks():
    assert decompose("") == []


def test_decompose_whitespace_only_returns_no_tasks():
    assert decompose("   \n\t  ") == []


def test_decompose_single_sentence_becomes_one_task():
    tasks = decompose("Check the server health")

    assert len(tasks) == 1
    assert tasks[0].description == "Check the server health"
    assert tasks[0].agent_type == route("Check the server health")


def test_decompose_splits_on_sentence_boundaries():
    tasks = decompose("Check server health. Generate a report!")

    assert [task.description for task in tasks] == [
        "Check server health",
        "Generate a report",
    ]


def test_decompose_splits_on_question_mark():
    tasks = decompose("What is the topology? Summarize it.")

    assert [task.description for task in tasks] == [
        "What is the topology",
        "Summarize it",
    ]


def test_decompose_splits_on_and_then_within_a_sentence():
    tasks = decompose("Check the logs and then generate a report")

    assert [task.description for task in tasks] == [
        "Check the logs",
        "generate a report",
    ]


def test_decompose_each_task_routed_to_its_own_fragment():
    tasks = decompose("Check server cpu load. Please review this change.")

    # INFRASTRUCTURE, not MONITORING: this fragment matches both
    # "server" (infrastructure) and "cpu" (monitoring), and ``route``'s
    # own documented tie-break is that the *longest* matched keyword
    # wins -- table order carries no meaning.
    assert tasks[0].agent_type == AgentType.INFRASTRUCTURE
    assert tasks[1].agent_type == AgentType.REVIEWER


def test_decompose_respects_default_max_tasks_of_four():
    request = ". ".join(f"do step {n}" for n in range(6))

    tasks = decompose(request)

    assert len(tasks) == 4
    assert [task.description for task in tasks] == [
        "do step 0",
        "do step 1",
        "do step 2",
        "do step 3",
    ]


def test_decompose_respects_custom_max_tasks():
    request = ". ".join(f"do step {n}" for n in range(6))

    tasks = decompose(request, max_tasks=2)

    assert len(tasks) == 2


# ---- select_dynamically() -----------------------------------------------------------


def _agent(
    *, slug: str, consecutive_failures: int = 0, last_executed_at: datetime | None = None
) -> Agent:
    return Agent(
        organization_id=uuid.uuid4(),
        slug=slug,
        name=slug,
        agent_type=AgentType.EXECUTOR,
        consecutive_failures=consecutive_failures,
        last_executed_at=last_executed_at,
    )


def test_select_dynamically_returns_none_for_no_candidates():
    assert select_dynamically([]) is None


def test_select_dynamically_returns_only_candidate():
    solo = _agent(slug="solo")

    assert select_dynamically([solo]) is solo


def test_select_dynamically_prefers_fewest_consecutive_failures():
    healthy = _agent(slug="healthy", consecutive_failures=0)
    struggling = _agent(slug="struggling", consecutive_failures=3)

    assert select_dynamically([struggling, healthy]) is healthy


def test_select_dynamically_tie_breaks_on_most_recent_activity():
    now = datetime.now(UTC)
    stale = _agent(slug="stale", consecutive_failures=1, last_executed_at=now.replace(year=2020))
    fresh = _agent(slug="fresh", consecutive_failures=1, last_executed_at=now)

    assert select_dynamically([stale, fresh]) is fresh


def test_select_dynamically_treats_never_executed_as_least_recent():
    never_run = _agent(slug="never-run", consecutive_failures=0, last_executed_at=None)
    ran_long_ago = _agent(
        slug="ran-long-ago",
        consecutive_failures=0,
        last_executed_at=datetime(2000, 1, 1, tzinfo=UTC),
    )

    assert select_dynamically([never_run, ran_long_ago]) is ran_long_ago


# ---- AgentOrchestrator.agent_for() ---------------------------------------------------


def test_agent_for_resolves_matching_type(model_registry):
    monitor = _agent(slug="monitor")
    orchestrator = AgentOrchestrator(model_registry, {AgentType.MONITORING: [monitor]}, {})

    task = AgentTask(description="check cpu", agent_type=AgentType.MONITORING)

    assert orchestrator.agent_for(task) is monitor


def test_agent_for_falls_back_to_executor_type(model_registry):
    executor = _agent(slug="executor")
    orchestrator = AgentOrchestrator(model_registry, {AgentType.EXECUTOR: [executor]}, {})

    task = AgentTask(description="check cpu", agent_type=AgentType.MONITORING)

    assert orchestrator.agent_for(task) is executor


def test_agent_for_returns_none_when_nothing_matches(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})

    task = AgentTask(description="check cpu", agent_type=AgentType.MONITORING)

    assert orchestrator.agent_for(task) is None


# ---- AgentOrchestrator.run_one() -- deterministic failure paths ----------------------


async def test_run_one_returns_failure_when_no_agent_registered(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    task = AgentTask(description="do something", agent_type=AgentType.MONITORING)

    result = await orchestrator.run_one(task, SharedMemory())

    assert result.succeeded is False
    assert result.agent_name == "unassigned"
    assert result.content == ""
    assert "No agent registered for" in (result.error or "")
    assert result.task is task


async def test_run_one_returns_failure_when_agent_has_no_profile(
    model_registry, agents_repo, organization_id
):
    agent = await agents_repo.create(
        Agent(
            organization_id=organization_id,
            slug="profile-less",
            name="Profile-less",
            agent_type=AgentType.EXECUTOR,
        )
    )
    orchestrator = AgentOrchestrator(model_registry, {AgentType.EXECUTOR: [agent]}, {})
    task = AgentTask(description="do something", agent_type=AgentType.EXECUTOR)

    result = await orchestrator.run_one(task, SharedMemory())

    assert result.succeeded is False
    assert result.agent_name == agent.name
    assert "has no configuration profile" in (result.error or "")


# ---- AgentOrchestrator.run_one() -- real dispatch, success or failure accepted -------


async def test_run_one_real_dispatch_returns_well_formed_result(
    model_registry, make_agent, profiles_repo
):
    agent = await make_agent(slug="dispatcher", agent_type=AgentType.EXECUTOR)
    profile = await profiles_repo.get_for_agent(agent.id)
    orchestrator = AgentOrchestrator(
        model_registry, {AgentType.EXECUTOR: [agent]}, {agent.id: profile}
    )
    task = AgentTask(description="Say hello in one word.", agent_type=AgentType.EXECUTOR)

    result = await orchestrator.run_one(task, SharedMemory())

    assert result.task is task
    assert result.agent_name == agent.name
    if result.succeeded:
        assert result.content
        assert result.error is None
    else:
        assert result.content == ""
        assert result.error


# ---- run_sequential() / run_parallel() -----------------------------------------------


async def test_run_sequential_runs_every_task_and_never_raises(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    tasks = [
        AgentTask(description="first", agent_type=AgentType.MONITORING),
        AgentTask(description="second", agent_type=AgentType.SECURITY),
    ]

    results = await orchestrator.run_sequential(tasks)

    assert [result.task for result in results] == tasks
    assert all(result.succeeded is False for result in results)
    assert "monitoring" in (results[0].error or "")
    assert "security" in (results[1].error or "")


async def test_run_parallel_empty_list_returns_empty(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    assert await orchestrator.run_parallel([]) == []


async def test_run_parallel_runs_every_task_and_never_raises(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {}, max_parallel_agents=1)
    tasks = [
        AgentTask(description="a", agent_type=AgentType.MONITORING),
        AgentTask(description="b", agent_type=AgentType.SECURITY),
        AgentTask(description="c", agent_type=AgentType.REPORTING),
    ]

    results = await orchestrator.run_parallel(tasks)

    assert len(results) == 3
    assert all(result.succeeded is False for result in results)
    assert {result.task.description for result in results} == {"a", "b", "c"}


# ---- aggregate() ------------------------------------------------------------------


def test_aggregate_empty_results_returns_empty_string():
    assert aggregate([]) == ""


def test_aggregate_single_success_returns_bare_content():
    result = AgentResult(
        task=AgentTask(description="x", agent_type=AgentType.EXECUTOR),
        agent_name="a",
        content="the answer",
        succeeded=True,
    )
    assert aggregate([result]) == "the answer"


def test_aggregate_single_failure_reports_the_gap():
    task = AgentTask(description="check the thing", agent_type=AgentType.EXECUTOR)
    result = AgentResult(task=task, agent_name="a", content="", succeeded=False, error="boom")

    assert aggregate([result]) == "[Could not complete 'check the thing': boom]"


def test_aggregate_failure_with_no_error_message_uses_fallback_text():
    task = AgentTask(description="check the thing", agent_type=AgentType.EXECUTOR)
    result = AgentResult(task=task, agent_name="a", content="", succeeded=False, error=None)

    assert aggregate([result]) == "[Could not complete 'check the thing': unknown error]"


def test_aggregate_mixes_success_and_failure_sections():
    ok_task = AgentTask(description="ok task", agent_type=AgentType.EXECUTOR)
    bad_task = AgentTask(description="bad task", agent_type=AgentType.EXECUTOR)
    results = [
        AgentResult(task=ok_task, agent_name="a", content="all good", succeeded=True),
        AgentResult(task=bad_task, agent_name="b", content="", succeeded=False, error="offline"),
    ]

    combined = aggregate(results)

    assert "all good" in combined
    assert "[Could not complete 'bad task': offline]" in combined
    assert combined.index("all good") < combined.index("[Could not complete")
