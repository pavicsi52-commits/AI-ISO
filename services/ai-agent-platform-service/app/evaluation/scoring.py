"""Pure scoring functions (docs/060 "EVALUATION": Task Accuracy,
Execution Quality, Reasoning Quality, Tool Success Rate).

A genuine gap: nothing in this platform scores an execution's own
quality. Two different scoring styles are used deliberately:

- **Structural** (:func:`score_tool_success_rate`,
  :func:`score_execution_quality`, :func:`score_reasoning_efficiency`)
  -- computed straight from an :class:`~app.models.execution
  .AgentExecution`'s own trace and counters. Free, deterministic,
  always available.
- **Judged** (:func:`score_task_accuracy_with_model`) -- correctness
  against an expected answer is a semantic question a token-overlap
  heuristic answers badly (two answers can agree completely while
  sharing almost no words), so this asks a model to judge it, with
  :func:`score_task_accuracy_lexical` as the free, deterministic
  fallback when no model call is available or the judge's own reply
  cannot be parsed.
"""

from __future__ import annotations

import re

from shared_core.exceptions.ai import AIError

from app.clients.base import ChatMessage
from app.clients.dispatch import dispatch_chat
from app.clients.registry import ModelRegistry
from app.models.execution import AgentExecution
from app.models.profile import AgentProfile

_SCORE_PATTERN = re.compile(r"(\d*\.\d+|\d+)")


def score_tool_success_rate(execution: AgentExecution) -> float | None:
    """Fraction of this execution's own tool calls that succeeded, or
    ``None`` when it made none -- there is nothing to rate."""
    tool_calls = [entry for entry in execution.trace if entry.get("type") == "tool_call"]
    if not tool_calls:
        return None
    succeeded = sum(1 for entry in tool_calls if entry.get("status") == "succeeded")
    return succeeded / len(tool_calls)


def score_execution_quality(execution: AgentExecution) -> float:
    """``1.0`` for a clean, error-free execution; penalised for a
    terminal error and for denied/failed tool calls along the way.
    """
    if execution.error:
        return 0.0

    tool_calls = [entry for entry in execution.trace if entry.get("type") == "tool_call"]
    if not tool_calls:
        return 1.0
    unhealthy = sum(1 for entry in tool_calls if entry.get("status") in ("denied", "failed"))
    return max(0.0, 1.0 - (unhealthy / len(tool_calls)))


def score_reasoning_efficiency(
    execution: AgentExecution, *, max_reasoning_steps: int
) -> float | None:
    """How efficiently a reasoning loop used its own step budget, or
    ``None`` when it took no explicit steps (a single-shot Chain-of-
    Thought call has nothing to rate here).

    A run that finished well under budget scores high; one that
    exhausted its budget scores low, doubly so if it still ended in
    error -- spending every available step and still failing is the
    worst outcome this metric can describe.
    """
    if execution.reasoning_steps <= 0:
        return None
    budget = max(1, max_reasoning_steps)
    efficiency = max(0.0, 1.0 - (execution.reasoning_steps / budget))
    if execution.error:
        efficiency *= 0.5
    return efficiency


def score_task_accuracy_lexical(actual: str, expected: str) -> float:
    """Deterministic, judge-free fallback: token-set Jaccard similarity
    between *actual* and *expected*.

    A cheap proxy, not a semantic judgement -- two answers phrased
    differently but equally correct can score low here, which is
    exactly why :func:`score_task_accuracy_with_model` exists.
    """
    expected_tokens = set(expected.lower().split())
    actual_tokens = set(actual.lower().split())
    if not expected_tokens:
        return 1.0 if not actual_tokens else 0.0
    union = actual_tokens | expected_tokens
    if not union:
        return 1.0
    return len(actual_tokens & expected_tokens) / len(union)


async def score_task_accuracy_with_model(
    registry: ModelRegistry,
    profile: AgentProfile,
    *,
    request: str,
    actual: str,
    expected: str,
) -> float:
    """Ask a model to judge how well *actual* answers *request*
    compared to *expected*, as a single ``0.0``-``1.0`` score.

    Falls back to :func:`score_task_accuracy_lexical` when the judge
    call fails or its reply carries no parseable number -- a
    correctness score should degrade to something deterministic, never
    to nothing.
    """
    prompt = (
        "Score how well the ACTUAL answer addresses the REQUEST, using the "
        "EXPECTED answer as the reference for what a correct answer looks "
        "like. Reply with only a single number from 0.0 (completely wrong) "
        f"to 1.0 (fully correct).\n\nRequest: {request}\n\nExpected: "
        f"{expected}\n\nActual: {actual}"
    )
    try:
        completion = await dispatch_chat(
            registry, profile, [ChatMessage(role="user", content=prompt)]
        )
    except AIError:
        return score_task_accuracy_lexical(actual, expected)

    match = _SCORE_PATTERN.search(completion.content)
    if not match:
        return score_task_accuracy_lexical(actual, expected)
    return max(0.0, min(1.0, float(match.group(1))))


__all__ = [
    "score_execution_quality",
    "score_reasoning_efficiency",
    "score_task_accuracy_lexical",
    "score_task_accuracy_with_model",
    "score_tool_success_rate",
]
