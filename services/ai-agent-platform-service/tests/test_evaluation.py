"""Tests for :mod:`app.evaluation.scoring` and :mod:`app.evaluation.service`.

The four structural scorers are pure functions over an
:class:`~app.models.execution.AgentExecution`'s own trace/counters, so
they are exercised with real, transient execution objects carrying
exactly the trace shapes this service actually writes
(``app/tool_execution/executor.py`` and ``app/reasoning/engine.py`` both
append ``{"type": "tool_call", ...}`` entries, the latter *without* a
``status`` key when no tool was registered under the requested name).

``score_task_accuracy_with_model`` and ``EvaluationService`` are
exercised against three genuinely real model backends, never a mock:

- the conftest ``model_registry``, whose real outcome in an environment
  with no local model daemon is a real ``AIError`` -- an accepted,
  expected outcome per ``tests/conftest.py``'s own module docstring;
- :data:`UNREACHABLE_BASE_URL`, a real loopback port nothing listens
  on, for a *deterministic* judge failure;
- :class:`LocalModelServer`, a genuine ``http.server`` on ``127.0.0.1``
  speaking Ollama's own ``POST /api/chat`` wire format. The judge's own
  reply-*parsing* branches (a parseable score, an unparseable reply, an
  out-of-range score) are unreachable behind a failing backend, and a
  real local HTTP round trip is the only way to reach them without a
  live vendor account -- the same approach ``tests/test_clients.py``
  already takes for a provider client's own success path.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from app.clients.ollama_client import OllamaClient
from app.clients.registry import ModelRegistry
from app.evaluation.scoring import (
    score_execution_quality,
    score_reasoning_efficiency,
    score_task_accuracy_lexical,
    score_task_accuracy_with_model,
    score_tool_success_rate,
)
from app.evaluation.service import EvaluationService
from app.models.enums import ExecutionStatus, ModelProvider, RoutingStrategy
from app.models.execution import AgentExecution
from app.models.profile import AgentProfile
from app.repositories.evaluation import AgentEvaluationRepository
from app.repositories.execution import AgentExecutionRepository
from tests.conftest import utcnow

UNREACHABLE_BASE_URL = "http://127.0.0.1:1"
"""A real loopback port nothing listens on: fails fast, never mocked."""


# ---- a genuine local model backend, not a mock of the registry ----------------


class LocalModelServer:
    """A real ``http.server`` on ``127.0.0.1`` speaking Ollama's own
    ``POST /api/chat``, run in a background thread.

    Queued replies are served in order, oldest first, and every prompt
    actually received is recorded. Real sockets, real HTTP/1.1: the
    ``ModelRegistry`` under test is the production one and never knows
    this isn't a real daemon.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self._replies: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.prompts.append(str(body["messages"][-1]["content"]))
                reply = outer._replies.pop(0) if outer._replies else ""
                payload = json.dumps(
                    {
                        "model": body.get("model", "llama3"),
                        "message": {"role": "assistant", "content": reply},
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 7,
                        "eval_count": 3,
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, log_format: str, *args: Any) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def queue_reply(self, content: str) -> None:
        """Queue one reply; an exhausted queue serves an empty reply."""
        self._replies.append(content)

    def registry(self, http_client: httpx.AsyncClient) -> ModelRegistry:
        """A real :class:`ModelRegistry` whose only provider is this server."""
        return ModelRegistry(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=self.base_url)},
            default_provider=ModelProvider.OLLAMA,
            default_model="llama3",
        )

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


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


def judge_profile(**overrides: Any) -> AgentProfile:
    """A transient profile carrying only what ``dispatch_chat`` reads."""
    defaults: dict[str, Any] = {
        "model_provider": ModelProvider.OLLAMA,
        "routing_strategy": RoutingStrategy.FALLBACK,
        "model_name": "llama3",
        "temperature": 0.0,
        "max_tokens": 16,
    }
    defaults.update(overrides)
    return AgentProfile(**defaults)


# ---- execution / trace builders -----------------------------------------------


def tool_call(status: str | None = "succeeded", *, tool_key: str = "lookup") -> dict[str, object]:
    """One ``tool_call`` trace entry in the shape this service writes.

    ``status=None`` reproduces ``app/reasoning/engine.py``'s own "no tool
    registered under that name" entry, which carries an ``error`` and no
    ``status`` at all.
    """
    entry: dict[str, object] = {"type": "tool_call", "tool_key": tool_key}
    if status is None:
        entry["error"] = f"Tool call was not executed: no tool registered as {tool_key!r}."
    else:
        entry["status"] = status
    return entry


def an_execution(
    *,
    trace: list[dict[str, object]] | None = None,
    error: str | None = None,
    reasoning_steps: int = 0,
) -> AgentExecution:
    """A transient execution carrying only what the scorers read."""
    return AgentExecution(trace=list(trace or []), error=error, reasoning_steps=reasoning_steps)


# ---- score_tool_success_rate() -------------------------------------------------


def test_tool_success_rate_is_none_for_an_empty_trace():
    assert score_tool_success_rate(an_execution()) is None


def test_tool_success_rate_is_none_when_the_trace_holds_no_tool_calls():
    execution = an_execution(
        trace=[{"type": "plan", "content": "think"}, {"type": "final", "content": "done"}]
    )

    assert score_tool_success_rate(execution) is None


def test_tool_success_rate_is_one_when_every_call_succeeded():
    execution = an_execution(trace=[tool_call(), tool_call(), tool_call()])

    assert score_tool_success_rate(execution) == 1.0


def test_tool_success_rate_is_zero_when_every_call_failed():
    execution = an_execution(trace=[tool_call("failed"), tool_call("denied")])

    assert score_tool_success_rate(execution) == 0.0


def test_tool_success_rate_is_the_succeeded_fraction():
    execution = an_execution(
        trace=[tool_call(), tool_call("failed"), tool_call("denied"), tool_call(None)]
    )

    assert score_tool_success_rate(execution) == 0.25


def test_tool_success_rate_counts_a_status_less_entry_as_not_succeeded():
    execution = an_execution(trace=[tool_call(), tool_call(None)])

    assert score_tool_success_rate(execution) == 0.5


def test_tool_success_rate_ignores_non_tool_entries_in_the_denominator():
    execution = an_execution(
        trace=[
            {"type": "plan", "content": "think"},
            tool_call(),
            {"type": "step", "index": 1},
            tool_call("failed"),
            {"type": "final", "content": "done"},
        ]
    )

    assert score_tool_success_rate(execution) == 0.5


# ---- score_execution_quality() -------------------------------------------------


def test_execution_quality_is_one_for_a_clean_run_with_no_tool_calls():
    assert score_execution_quality(an_execution()) == 1.0


def test_execution_quality_is_one_when_only_non_tool_entries_are_traced():
    execution = an_execution(trace=[{"type": "draft", "content": "x"}])

    assert score_execution_quality(execution) == 1.0


def test_execution_quality_is_one_when_every_tool_call_succeeded():
    execution = an_execution(trace=[tool_call(), tool_call()])

    assert score_execution_quality(execution) == 1.0


def test_execution_quality_is_zero_for_a_terminal_error():
    assert score_execution_quality(an_execution(error="provider unreachable")) == 0.0


def test_execution_quality_ignores_healthy_tool_calls_once_the_run_errored():
    execution = an_execution(trace=[tool_call(), tool_call()], error="timed out")

    assert score_execution_quality(execution) == 0.0


def test_execution_quality_penalises_one_denied_call_of_four():
    execution = an_execution(trace=[tool_call(), tool_call(), tool_call(), tool_call("denied")])

    assert score_execution_quality(execution) == 0.75


def test_execution_quality_penalises_denied_and_failed_calls_alike():
    execution = an_execution(
        trace=[tool_call(), tool_call("denied"), tool_call("failed"), tool_call()]
    )

    assert score_execution_quality(execution) == 0.5


def test_execution_quality_bottoms_out_at_zero_when_every_call_is_unhealthy():
    execution = an_execution(trace=[tool_call("denied"), tool_call("failed")])

    assert score_execution_quality(execution) == 0.0


def test_execution_quality_does_not_penalise_in_flight_statuses():
    execution = an_execution(trace=[tool_call("pending"), tool_call("running")])

    assert score_execution_quality(execution) == 1.0


def test_execution_quality_does_not_penalise_a_status_less_entry():
    # Deliberate asymmetry with score_tool_success_rate, which counts the
    # same entry as "not succeeded": only an explicitly denied/failed call
    # is evidence the *run* went badly.
    execution = an_execution(trace=[tool_call(None)])

    assert score_execution_quality(execution) == 1.0
    assert score_tool_success_rate(execution) == 0.0


# ---- score_reasoning_efficiency() ----------------------------------------------


def test_reasoning_efficiency_is_none_when_no_explicit_steps_were_taken():
    assert score_reasoning_efficiency(an_execution(), max_reasoning_steps=8) is None


def test_reasoning_efficiency_is_none_for_a_negative_step_count():
    execution = an_execution(reasoning_steps=-1)

    assert score_reasoning_efficiency(execution, max_reasoning_steps=8) is None


def test_reasoning_efficiency_rewards_finishing_well_under_budget():
    execution = an_execution(reasoning_steps=2)

    assert score_reasoning_efficiency(execution, max_reasoning_steps=8) == 0.75


def test_reasoning_efficiency_is_zero_when_the_budget_was_exhausted():
    execution = an_execution(reasoning_steps=8)

    assert score_reasoning_efficiency(execution, max_reasoning_steps=8) == 0.0


def test_reasoning_efficiency_floors_at_zero_when_the_budget_was_overrun():
    execution = an_execution(reasoning_steps=12)

    assert score_reasoning_efficiency(execution, max_reasoning_steps=8) == 0.0


def test_reasoning_efficiency_halves_when_the_run_also_errored():
    execution = an_execution(reasoning_steps=2, error="gave up")

    assert score_reasoning_efficiency(execution, max_reasoning_steps=8) == 0.375


def test_reasoning_efficiency_worst_case_is_a_budget_burned_on_a_failure():
    execution = an_execution(reasoning_steps=8, error="gave up")

    assert score_reasoning_efficiency(execution, max_reasoning_steps=8) == 0.0


@pytest.mark.parametrize("max_reasoning_steps", [0, -3])
def test_reasoning_efficiency_clamps_a_non_positive_budget_to_one(max_reasoning_steps: int):
    # Without the clamp this would be a ZeroDivisionError, not a score.
    execution = an_execution(reasoning_steps=1)

    assert score_reasoning_efficiency(execution, max_reasoning_steps=max_reasoning_steps) == 0.0


def test_reasoning_efficiency_scales_with_the_budget_it_is_given():
    execution = an_execution(reasoning_steps=1)

    assert score_reasoning_efficiency(execution, max_reasoning_steps=4) == 0.75
    assert score_reasoning_efficiency(execution, max_reasoning_steps=2) == 0.5


# ---- score_task_accuracy_lexical() ---------------------------------------------


def test_lexical_accuracy_is_one_for_an_identical_answer():
    assert score_task_accuracy_lexical("the cat sat", "the cat sat") == 1.0


def test_lexical_accuracy_is_case_insensitive():
    assert score_task_accuracy_lexical("The CAT Sat", "the cat sat") == 1.0


def test_lexical_accuracy_ignores_repeated_tokens():
    assert score_task_accuracy_lexical("cat cat cat", "cat") == 1.0


def test_lexical_accuracy_is_zero_for_completely_disjoint_answers():
    assert score_task_accuracy_lexical("alpha beta", "gamma delta") == 0.0


def test_lexical_accuracy_is_token_set_jaccard_for_a_partial_overlap():
    # {the, cat, sat} & {the, cat, ran} == 2; union == 4.
    assert score_task_accuracy_lexical("the cat sat", "the cat ran") == 0.5


def test_lexical_accuracy_penalises_a_verbose_but_containing_answer():
    # {the, cat, sat, on, mat} & {the, cat} == 2; union == 5.
    assert score_task_accuracy_lexical("the cat sat on mat", "the cat") == 0.4


def test_lexical_accuracy_treats_an_empty_expected_and_empty_actual_as_correct():
    assert score_task_accuracy_lexical("", "") == 1.0


def test_lexical_accuracy_treats_whitespace_only_expected_as_empty():
    assert score_task_accuracy_lexical("   ", "  \t \n ") == 1.0


def test_lexical_accuracy_is_zero_when_nothing_was_expected_but_something_was_said():
    assert score_task_accuracy_lexical("unexpected words", "") == 0.0


def test_lexical_accuracy_is_zero_when_something_was_expected_but_nothing_was_said():
    assert score_task_accuracy_lexical("", "the cat sat") == 0.0


def test_lexical_accuracy_does_not_strip_punctuation():
    # The documented cheapness of the fallback: "hello!" and "hello" are
    # different tokens, which is exactly why the model judge exists.
    assert score_task_accuracy_lexical("hello!", "hello") == 0.0


# ---- score_task_accuracy_with_model() -- real judge, real HTTP ------------------


async def test_model_judge_falls_back_to_lexical_when_the_backend_is_unreachable(
    http_client: httpx.AsyncClient,
):
    score = await score_task_accuracy_with_model(
        unreachable_registry(http_client),
        judge_profile(),
        request="What did the cat do?",
        actual="the cat sat",
        expected="the cat ran",
    )

    assert score == score_task_accuracy_lexical("the cat sat", "the cat ran")
    assert score == 0.5


async def test_model_judge_falls_back_to_lexical_with_the_real_shared_registry(
    model_registry: ModelRegistry,
):
    # The conftest registry is the real one; with no model daemon running
    # every provider in its chain genuinely fails, and the contract is
    # that a correctness score degrades to something deterministic.
    score = await score_task_accuracy_with_model(
        model_registry,
        judge_profile(),
        request="What did the cat do?",
        actual="the cat sat",
        expected="the cat sat",
    )

    assert 0.0 <= score <= 1.0


async def test_model_judge_uses_the_score_the_judge_actually_returned(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    model_server.queue_reply("0.75")

    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="What did the cat do?",
        actual="the cat sat",
        expected="the cat sat",
    )

    # Lexical would have said 1.0 here, so 0.75 can only be the judge's.
    assert score == 0.75


async def test_model_judge_extracts_a_score_embedded_in_prose(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    model_server.queue_reply("Score: 0.9 -- mostly right, one detail missing.")

    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="q",
        actual="alpha",
        expected="beta",
    )

    assert score == 0.9


@pytest.mark.parametrize(("reply", "expected_score"), [("1", 1.0), ("0", 0.0)])
async def test_model_judge_accepts_a_bare_integer_score(
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    reply: str,
    expected_score: float,
):
    model_server.queue_reply(reply)

    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="q",
        actual="alpha",
        expected="beta gamma",
    )

    assert score == expected_score


async def test_model_judge_clamps_a_score_above_one(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    model_server.queue_reply("1.5")

    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="q",
        actual="alpha",
        expected="beta",
    )

    # Lexical would have said 0.0 for these disjoint answers.
    assert score == 1.0


async def test_model_judge_reads_an_unsigned_number_out_of_a_negative_reply(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    # The extraction pattern carries no sign, so "-0.4" reads as 0.4.
    # Documented here because it is the one reply shape whose parsed
    # value differs from what a human reader would expect.
    model_server.queue_reply("-0.4")

    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="q",
        actual="alpha",
        expected="beta",
    )

    assert score == 0.4


async def test_model_judge_falls_back_to_lexical_for_an_unparseable_reply(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    model_server.queue_reply("I cannot judge this without more context.")

    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="q",
        actual="the cat sat",
        expected="the cat ran",
    )

    assert score == 0.5


async def test_model_judge_falls_back_to_lexical_for_an_empty_reply(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    # No reply queued: the server answers with an empty message content.
    score = await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="q",
        actual="the cat sat",
        expected="the cat ran",
    )

    assert score == 0.5
    assert model_server.prompts != []


async def test_model_judge_prompt_carries_the_request_expected_and_actual(
    http_client: httpx.AsyncClient, model_server: LocalModelServer
):
    model_server.queue_reply("0.5")

    await score_task_accuracy_with_model(
        model_server.registry(http_client),
        judge_profile(),
        request="What did the cat do?",
        actual="the cat sat",
        expected="the cat ran",
    )

    prompt = model_server.prompts[0]
    assert prompt.startswith("Score how well the ACTUAL answer addresses the REQUEST")
    assert "Request: What did the cat do?" in prompt
    assert "Expected: the cat ran" in prompt
    assert "Actual: the cat sat" in prompt


# ---- EvaluationService.evaluate_execution() ------------------------------------


async def persisted_execution(
    executions_repo: AgentExecutionRepository,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    **overrides: Any,
) -> AgentExecution:
    """A real ``agent_executions`` row to evaluate."""
    defaults: dict[str, Any] = {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "status": ExecutionStatus.COMPLETED,
        "started_at": utcnow(),
        "completed_at": utcnow(),
        "trace": [tool_call(), tool_call("failed")],
        "reasoning_steps": 2,
        "latency_ms": 123.5,
        "cost_usd": 0.25,
        "input_summary": "What did the cat do?",
        "output_summary": "the cat sat",
    }
    defaults.update(overrides)
    return await executions_repo.create(AgentExecution(**defaults))


async def test_evaluate_execution_scores_every_structural_metric(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="scored-agent")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)
    service = EvaluationService(evaluations_repo)

    evaluation = await service.evaluate_execution(execution)

    assert evaluation.organization_id == organization_id
    assert evaluation.agent_id == agent.id
    assert evaluation.execution_id == execution.id
    assert evaluation.task_accuracy is None
    assert evaluation.execution_quality == 0.5
    assert evaluation.reasoning_quality == 0.75
    assert evaluation.tool_success_rate == 0.5
    assert evaluation.latency_ms == 123.5
    assert evaluation.cost_usd == 0.25
    assert evaluation.human_feedback_score is None
    assert evaluation.is_regression_test is False
    assert evaluation.evaluated_by is None


async def test_evaluate_execution_leaves_unscoreable_metrics_null(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="single-shot")
    execution = await persisted_execution(
        executions_repo, organization_id, agent.id, trace=[], reasoning_steps=0
    )

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(execution)

    assert evaluation.tool_success_rate is None
    assert evaluation.reasoning_quality is None
    assert evaluation.execution_quality == 1.0


async def test_evaluate_execution_of_a_failed_run_scores_zero_and_halves_reasoning(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="failed-run")
    execution = await persisted_execution(
        executions_repo,
        organization_id,
        agent.id,
        status=ExecutionStatus.FAILED,
        error="Every model provider in the fallback chain failed.",
        trace=[tool_call()],
        reasoning_steps=4,
    )

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(execution)

    assert evaluation.execution_quality == 0.0
    assert evaluation.reasoning_quality == 0.25
    assert evaluation.tool_success_rate == 1.0


async def test_evaluate_execution_honours_a_custom_reasoning_budget(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="tight-budget")
    execution = await persisted_execution(
        executions_repo, organization_id, agent.id, reasoning_steps=1
    )

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution, max_reasoning_steps=4
    )

    assert evaluation.reasoning_quality == 0.75


async def test_evaluate_execution_scores_accuracy_lexically_without_a_judge(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="lexical-accuracy")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution, expected_output="the cat ran"
    )

    assert evaluation.task_accuracy == 0.5


async def test_evaluate_execution_needs_both_registry_and_profile_to_use_the_judge(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="half-configured-judge")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)
    service = EvaluationService(evaluations_repo)

    registry_only = await service.evaluate_execution(
        execution, expected_output="the cat ran", registry=model_server.registry(http_client)
    )
    profile_only = await service.evaluate_execution(
        execution, expected_output="the cat ran", judge_profile=judge_profile()
    )

    # Neither half is enough, so neither call reached the judge at all.
    assert registry_only.task_accuracy == 0.5
    assert profile_only.task_accuracy == 0.5
    assert model_server.prompts == []


async def test_evaluate_execution_uses_the_real_judge_when_both_are_supplied(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    make_agent,
    organization_id,
):
    model_server.queue_reply("0.8")
    agent = await make_agent(slug="judged-agent")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution,
        expected_output="the cat ran",
        registry=model_server.registry(http_client),
        judge_profile=judge_profile(),
    )

    # Lexical would have scored 0.5, so 0.8 is the judge's own verdict.
    assert evaluation.task_accuracy == 0.8
    assert "Request: What did the cat do?" in model_server.prompts[0]
    assert "Actual: the cat sat" in model_server.prompts[0]


async def test_evaluate_execution_judge_failure_degrades_to_the_lexical_score(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    http_client: httpx.AsyncClient,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="judge-offline")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution,
        expected_output="the cat ran",
        registry=unreachable_registry(http_client),
        judge_profile=judge_profile(),
    )

    assert evaluation.task_accuracy == 0.5


async def test_evaluate_execution_end_to_end_against_the_real_shared_registry(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    model_registry: ModelRegistry,
    profiles_repo,
    make_agent,
    organization_id,
):
    # The real registry and the agent's own real persisted profile. With
    # no model daemon running the judge genuinely fails and the lexical
    # fallback answers; with one running the judge answers. Either way a
    # score lands, and every structural metric is exact regardless.
    agent = await make_agent(slug="real-registry-eval")
    profile = await profiles_repo.get_for_agent(agent.id)
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution,
        expected_output="the cat ran",
        registry=model_registry,
        judge_profile=profile,
    )

    assert evaluation.task_accuracy is not None
    assert 0.0 <= evaluation.task_accuracy <= 1.0
    assert evaluation.execution_quality == 0.5
    assert evaluation.tool_success_rate == 0.5


async def test_evaluate_execution_treats_a_missing_output_summary_as_empty(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="no-output")
    execution = await persisted_execution(
        executions_repo, organization_id, agent.id, output_summary=None
    )

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution, expected_output="the cat ran"
    )

    assert evaluation.task_accuracy == 0.0


async def test_evaluate_execution_treats_a_missing_input_summary_as_an_empty_request(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    http_client: httpx.AsyncClient,
    model_server: LocalModelServer,
    make_agent,
    organization_id,
):
    model_server.queue_reply("0.6")
    agent = await make_agent(slug="no-input")
    execution = await persisted_execution(
        executions_repo, organization_id, agent.id, input_summary=None
    )

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution,
        expected_output="the cat ran",
        registry=model_server.registry(http_client),
        judge_profile=judge_profile(),
    )

    assert evaluation.task_accuracy == 0.6
    assert "Request: \n\nExpected: the cat ran" in model_server.prompts[0]


async def test_evaluate_execution_records_an_empty_expected_output_as_ground_truth(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    # "" is a real expectation ("say nothing"), not the absence of one --
    # only ``None`` means there is no ground truth to compare against.
    agent = await make_agent(slug="expects-silence")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution, expected_output=""
    )

    assert evaluation.task_accuracy == 0.0


async def test_evaluate_execution_carries_the_human_review_fields_through(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="human-reviewed")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution,
        human_feedback_score=0.6,
        is_regression_test=True,
        evaluated_by="qa@rithvisolution.com",
    )

    assert evaluation.human_feedback_score == 0.6
    assert evaluation.is_regression_test is True
    assert evaluation.evaluated_by == "qa@rithvisolution.com"


async def test_evaluate_execution_stamps_a_timezone_aware_evaluated_at(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="timestamped")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)
    before = utcnow()

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(execution)

    assert evaluation.evaluated_at.tzinfo is not None
    assert before <= evaluation.evaluated_at <= utcnow()


async def test_evaluate_execution_persists_a_retrievable_row(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    db_session,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="persisted-eval")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)

    evaluation = await EvaluationService(evaluations_repo).evaluate_execution(
        execution, expected_output="the cat ran", is_regression_test=True, evaluated_by="nightly"
    )
    # Read the identities out before expiring: a lazily refreshed
    # attribute on an AsyncSession would be implicit IO outside ``await``.
    evaluation_id, execution_id = evaluation.id, execution.id
    db_session.expire_all()
    reloaded = await evaluations_repo.get_by_id(evaluation_id)

    assert reloaded is not None
    assert reloaded.task_accuracy == 0.5
    assert reloaded.execution_quality == 0.5
    assert reloaded.reasoning_quality == 0.75
    assert reloaded.tool_success_rate == 0.5
    assert reloaded.is_regression_test is True
    assert reloaded.evaluated_by == "nightly"
    assert [row.id for row in await evaluations_repo.list_for_execution(execution_id)] == [
        evaluation_id
    ]


async def test_evaluate_execution_can_re_evaluate_the_same_execution(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    make_agent,
    organization_id,
):
    agent = await make_agent(slug="re-evaluated")
    execution = await persisted_execution(executions_repo, organization_id, agent.id)
    service = EvaluationService(evaluations_repo)

    first = await service.evaluate_execution(execution, evaluated_by="ci")
    second = await service.evaluate_execution(
        execution, is_regression_test=True, evaluated_by="nightly"
    )

    recorded = await evaluations_repo.list_for_execution(execution.id)

    assert {row.id for row in recorded} == {first.id, second.id}
    assert {row.evaluated_by for row in recorded} == {"ci", "nightly"}
