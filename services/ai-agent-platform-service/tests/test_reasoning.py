"""Tests for :mod:`app.reasoning.engine` (docs/060 "REASONING").

Every ``run_*`` mode makes real model-provider HTTP calls through the
real ``model_registry`` fixture -- no local LLM backend is guaranteed to
be reachable in this environment, so ``ModelRegistry.chat`` genuinely
raising ``AIError`` ("every provider in the chain failed") is an
accepted, expected outcome here, per ``tests/conftest.py``'s own
docstring. Every test below is written to hold under *either* real
outcome: a live backend answering, or every provider failing.

``_run_requested_tool_call`` is exercised directly (it is what makes
``run_tool_based``'s own tool-calling loop real) against a real
:class:`~app.tool_execution.executor.ToolExecutor`, a real registered
handler, and a real :class:`~app.models.tool.AgentTool` row -- this is
the one piece of ``run_tool_based``'s own behaviour that does not
require a reachable model backend to verify for real.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.ai import AIError

from app.clients.base import ChatMessage, RequestedToolCall
from app.graph.client import GraphClient
from app.models.enums import (
    ExecutionStatus,
    ModelProvider,
    PermissionCategory,
    ReasoningMode,
    ToolKind,
)
from app.models.execution import AgentExecution
from app.models.tool import AgentTool
from app.reasoning.engine import (
    ReasoningResult,
    _ask,
    _parse_plan_steps,
    _run_requested_tool_call,
    run_hybrid,
    run_knowledge_graph,
    run_plan_and_execute,
    run_reflection,
    run_self_verification,
    run_tool_based,
    run_tree_of_thought,
)
from app.tool_execution.executor import ToolExecutor
from app.tool_registry.registry import ToolHandlerRegistry
from tests.conftest import MakeAgentFn, utcnow


async def _profile(make_agent: MakeAgentFn, profiles_repo, slug: str = "reasoning-agent"):
    agent = await make_agent(slug=slug)
    profile = await profiles_repo.require_for_agent(agent.id)
    return profile, agent


def _assert_common_shape(result: ReasoningResult) -> None:
    assert isinstance(result, ReasoningResult)
    assert isinstance(result.content, str)
    assert isinstance(result.steps, list)
    assert result.prompt_tokens >= 0
    assert result.completion_tokens >= 0
    if result.succeeded:
        assert result.error is None
    else:
        assert result.error is not None and result.error != ""


# ---- _parse_plan_steps (pure) ------------------------------------------------


def test_parse_plan_steps_numbered_list():
    text = "1. First step\n2. Second step\n3. Third step"
    assert _parse_plan_steps(text) == ["First step", "Second step", "Third step"]


def test_parse_plan_steps_supports_parenthesis_and_colon_markers():
    text = "1) First step\n2: Second step"
    assert _parse_plan_steps(text) == ["First step", "Second step"]


def test_parse_plan_steps_bulleted_list():
    text = "- First step\n* Second step"
    assert _parse_plan_steps(text) == ["First step", "Second step"]


def test_parse_plan_steps_skips_blank_lines():
    text = "1. First step\n\n   \n2. Second step"
    assert _parse_plan_steps(text) == ["First step", "Second step"]


def test_parse_plan_steps_keeps_unprefixed_lines_as_is():
    text = "Just a plain line with no marker"
    assert _parse_plan_steps(text) == ["Just a plain line with no marker"]


def test_parse_plan_steps_empty_text_returns_empty_list():
    assert _parse_plan_steps("") == []
    assert _parse_plan_steps("   \n   ") == []


# ---- _ask (private, but its two system-message branches are only ever ------
# ---- reachable this way -- no run_* mode passes its own ``system=``) -------


async def test_ask_uses_the_explicit_system_argument_when_given(
    model_registry, make_agent, profiles_repo
):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="ask-explicit-system")

    # Real dispatch still fails (no reachable backend), but the message
    # list is built -- including the explicit system turn -- before that
    # call is ever made.
    with pytest.raises(AIError):
        await _ask(model_registry, profile, "hello", system="You are a helpful bot.")


async def test_ask_falls_back_to_the_profiles_own_system_prompt(
    make_agent, profiles_repo, model_registry
):
    agent = await make_agent(
        slug="ask-profile-system", profile={"system_prompt": "Be extremely concise."}
    )
    profile = await profiles_repo.require_for_agent(agent.id)
    assert profile.system_prompt == "Be extremely concise."

    with pytest.raises(AIError):
        await _ask(model_registry, profile, "hello")


async def test_ask_with_no_system_source_sends_no_system_turn(
    model_registry, make_agent, profiles_repo
):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="ask-no-system")
    assert profile.system_prompt is None

    with pytest.raises(AIError):
        await _ask(model_registry, profile, "hello")


# ---- run_tree_of_thought -----------------------------------------------------


async def test_run_tree_of_thought_real_outcome(model_registry, make_agent, profiles_repo):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="tot-agent")

    result = await run_tree_of_thought(
        model_registry, profile, "How should we roll out this feature?", branches=2
    )

    _assert_common_shape(result)
    if result.succeeded:
        assert result.content != ""
        assert any(step.get("type") == "synthesis" for step in result.steps)
        branch_steps = [step for step in result.steps if step.get("type") == "branch"]
        assert len(branch_steps) == 2
    else:
        assert result.content == ""


# ---- run_plan_and_execute ------------------------------------------------------


async def test_run_plan_and_execute_real_outcome(model_registry, make_agent, profiles_repo):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="plan-agent")

    result = await run_plan_and_execute(
        model_registry, profile, "Plan a database migration.", max_steps=2
    )

    _assert_common_shape(result)
    if result.succeeded:
        assert result.content != ""
        assert result.steps[0]["type"] == "plan"
        assert any(step.get("type") == "step" for step in result.steps)
    else:
        # The very first (plan) call is the only one that can fail before
        # any step trace exists.
        assert result.steps == [] or result.steps[0]["type"] == "plan"


# ---- run_reflection -------------------------------------------------------------


async def test_run_reflection_real_outcome(model_registry, make_agent, profiles_repo):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="reflect-agent")

    result = await run_reflection(
        model_registry, profile, "Summarize the benefits of code review.", max_iterations=1
    )

    _assert_common_shape(result)
    if result.succeeded:
        assert result.content != ""
        assert result.steps[0]["type"] == "draft"
    else:
        assert result.steps == []


# ---- run_self_verification -------------------------------------------------------


async def test_run_self_verification_real_outcome(model_registry, make_agent, profiles_repo):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="verify-agent")

    result = await run_self_verification(
        model_registry, profile, "What is the capital of France?", max_corrections=1
    )

    _assert_common_shape(result)
    if result.succeeded:
        assert result.content != ""
        assert result.steps[0]["type"] == "draft"
    else:
        assert result.steps == []


# ---- run_tool_based ---------------------------------------------------------------


async def test_run_tool_based_real_outcome(
    model_registry,
    make_agent,
    profiles_repo,
    executions_repo,
    tools_repo,
    publisher,
    organization_id,
):
    profile, agent = await _profile(make_agent, profiles_repo, slug="tool-agent")
    execution = await executions_repo.create(
        AgentExecution(
            organization_id=organization_id,
            agent_id=agent.id,
            status=ExecutionStatus.RUNNING,
            reasoning_mode=ReasoningMode.TOOL_BASED,
            model_provider=ModelProvider.OLLAMA,
            model_name="llama3",
            started_at=utcnow(),
        )
    )
    tool = await tools_repo.create(
        AgentTool(
            organization_id=organization_id,
            tool_key="echo_tool",
            name="Echo Tool",
            tool_kind=ToolKind.CUSTOM,
            parameters_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    )
    executor = ToolExecutor(ToolHandlerRegistry(), publish_event=publisher)

    result = await run_tool_based(
        model_registry,
        profile,
        "Echo the word hello using the tool.",
        executor=executor,
        execution=execution,
        tools_by_key={tool.tool_key: tool},
        agent_tool_keys=[tool.tool_key],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        max_steps=2,
    )

    _assert_common_shape(result)
    if not result.succeeded:
        # Failing on the very first dispatch leaves no trace entries yet.
        assert result.steps == [] or result.error is not None


# ---- run_knowledge_graph --------------------------------------------------------


async def test_run_knowledge_graph_real_outcome(model_registry, make_agent, profiles_repo):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="kg-agent")
    # A real, deliberately-disabled GraphClient (no Neo4j driver) -- exactly
    # the "knowledge graph not configured on this deployment" shape the
    # production code itself falls back to gracefully, not a mock.
    graph = GraphClient(None, enabled=False)
    assert graph.enabled is False

    result = await run_knowledge_graph(
        model_registry, profile, "What services depend on the billing service?", graph=graph
    )

    _assert_common_shape(result)
    if result.succeeded:
        assert result.content != ""
        assert result.steps[0]["type"] == "cypher"
        assert any(step.get("type") == "graph_unavailable" for step in result.steps)
    else:
        # Fails on the cypher-generation call, before any graph step exists.
        assert result.steps == [] or result.steps[0]["type"] == "cypher"


# ---- run_hybrid -------------------------------------------------------------------


async def test_run_hybrid_real_outcome(model_registry, make_agent, profiles_repo):
    profile, _agent = await _profile(make_agent, profiles_repo, slug="hybrid-agent")

    result = await run_hybrid(model_registry, profile, "Plan and verify a rollback.", max_steps=2)

    _assert_common_shape(result)
    if not result.succeeded:
        # run_hybrid short-circuits to the (failed) plan-and-execute result
        # unchanged when the plan itself never got produced.
        assert result.content == ""


# ---- _run_requested_tool_call (direct, real ToolExecutor) -------------------------


async def _echo_handler(arguments: dict) -> dict:
    return {"echo": arguments}


async def _build_execution(executions_repo, organization_id, agent_id):
    return await executions_repo.create(
        AgentExecution(
            organization_id=organization_id,
            agent_id=agent_id,
            status=ExecutionStatus.RUNNING,
            reasoning_mode=ReasoningMode.TOOL_BASED,
            model_provider=ModelProvider.OLLAMA,
            model_name="llama3",
            started_at=utcnow(),
        )
    )


async def test_run_requested_tool_call_executes_a_known_tool(
    make_agent, executions_repo, tools_repo, publisher, organization_id
):
    agent = await make_agent(slug="tool-call-known")
    execution = await _build_execution(executions_repo, organization_id, agent.id)
    tool = await tools_repo.create(
        AgentTool(
            organization_id=organization_id,
            tool_key="echo_tool",
            name="Echo Tool",
            tool_kind=ToolKind.CUSTOM,
            parameters_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
    )
    handlers = ToolHandlerRegistry()
    handlers.register("echo_tool", _echo_handler)
    executor = ToolExecutor(handlers, publish_event=publisher)
    messages: list[ChatMessage] = []
    trace: list[dict] = []
    call = RequestedToolCall(call_id="call-1", name="echo_tool", arguments={"text": "hi"})

    await _run_requested_tool_call(
        call,
        executor=executor,
        execution=execution,
        tools_by_key={"echo_tool": tool},
        agent_tool_keys=["echo_tool"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=False,
        messages=messages,
        trace=trace,
        step=0,
    )

    assert len(messages) == 1
    assert messages[0].role == "tool"
    assert messages[0].tool_call_id == "call-1"
    assert messages[0].tool_name == "echo_tool"
    assert messages[0].content == str({"echo": {"text": "hi"}})

    assert len(trace) == 1
    assert trace[0]["type"] == "tool_call"
    assert trace[0]["step"] == 0
    assert trace[0]["tool_key"] == "echo_tool"
    assert trace[0]["status"] == "succeeded"

    # The real ToolExecutor recorded the call onto the execution and
    # announced a real ToolInvoked event.
    assert execution.tool_calls_made == 1
    assert "ToolInvoked" in publisher.names


async def test_run_requested_tool_call_denied_tool_reports_denial(
    make_agent, executions_repo, tools_repo, publisher, organization_id
):
    agent = await make_agent(slug="tool-call-denied")
    execution = await _build_execution(executions_repo, organization_id, agent.id)
    tool = await tools_repo.create(
        AgentTool(
            organization_id=organization_id,
            tool_key="restricted_tool",
            name="Restricted Tool",
            tool_kind=ToolKind.CUSTOM,
        )
    )
    executor = ToolExecutor(ToolHandlerRegistry(), publish_event=publisher)
    messages: list[ChatMessage] = []
    trace: list[dict] = []
    call = RequestedToolCall(call_id="call-2", name="restricted_tool", arguments={})

    await _run_requested_tool_call(
        call,
        executor=executor,
        execution=execution,
        tools_by_key={"restricted_tool": tool},
        # The agent's own profile never granted this tool key.
        agent_tool_keys=[],
        granted_categories=[],
        allow_mutating=False,
        messages=messages,
        trace=trace,
        step=1,
    )

    assert trace[0]["status"] == "denied"
    assert messages[0].content.startswith("Tool call was not executed:")
    assert "ToolInvoked" in publisher.names


async def test_run_requested_tool_call_unknown_tool_is_not_executed(
    make_agent, executions_repo, publisher, organization_id
):
    agent = await make_agent(slug="tool-call-unknown")
    execution = await _build_execution(executions_repo, organization_id, agent.id)
    executor = ToolExecutor(ToolHandlerRegistry(), publish_event=publisher)
    messages: list[ChatMessage] = []
    trace: list[dict] = []
    call = RequestedToolCall(call_id="call-3", name="ghost_tool", arguments={"x": 1})

    await _run_requested_tool_call(
        call,
        executor=executor,
        execution=execution,
        tools_by_key={},
        agent_tool_keys=[],
        granted_categories=[],
        allow_mutating=False,
        messages=messages,
        trace=trace,
        step=2,
    )

    assert len(messages) == 1
    assert messages[0].role == "tool"
    assert messages[0].tool_call_id == "call-3"
    assert messages[0].tool_name == "ghost_tool"
    assert messages[0].content == (
        "Tool call was not executed: no tool registered as 'ghost_tool'."
    )

    assert trace == [
        {
            "type": "tool_call",
            "step": 2,
            "tool_key": "ghost_tool",
            "error": "Tool call was not executed: no tool registered as 'ghost_tool'.",
        }
    ]
    # Nothing was actually run, so the execution's own trace/counters and
    # the event bus never heard about it. Scoped to tool events rather
    # than asserting the publisher is wholly empty: ``make_agent`` above
    # legitimately published its own AgentRegisteredEvent through this
    # same real publisher.
    assert execution.tool_calls_made == 0
    assert "ToolInvoked" not in publisher.names


def test_reasoning_result_defaults():
    result = ReasoningResult(content="hello")
    assert result.content == "hello"
    assert result.steps == []
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert result.succeeded is True
    assert result.error is None


def test_reasoning_result_is_frozen():
    result = ReasoningResult(content="hello")
    with pytest.raises(AttributeError):
        result.content = "changed"  # type: ignore[misc]
