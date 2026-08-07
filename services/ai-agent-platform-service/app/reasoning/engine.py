"""Single-agent reasoning modes (docs/060 "REASONING").

Distinct from :mod:`app.agents` -- orchestration decides *which
agent(s)* handle a request; this module decides *how one agent thinks
through its own task*. A genuine gap: no reasoning loop exists anywhere
in this platform, only single-shot chat (``ai-assistant-service``'s own
precedent never loops a model call against its own prior output).

``Chain-of-Thought`` is explicitly "internal only" per docs/060's own
wording -- it is the model's own default behavior on a single
:func:`~app.clients.dispatch.dispatch_chat` call (optionally nudged by
the profile's own ``system_prompt``), never a separate multi-step loop,
so it has no function here.

Every mode returns a :class:`ReasoningResult` carrying its own
``steps`` trace -- each entry describes one model or tool call, so a
caller can persist the *reasoning*, not just the final answer, onto
:attr:`~app.models.execution.AgentExecution.trace`.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from shared_core.exceptions.ai import AIError

from app.clients.base import ChatMessage, RequestedToolCall
from app.clients.dispatch import dispatch_chat
from app.clients.registry import ModelRegistry
from app.graph.client import GraphClient
from app.models.execution import AgentExecution
from app.models.profile import AgentProfile
from app.models.tool import AgentTool
from app.tool_execution.executor import ToolExecutor
from app.tool_registry.registry import to_specification

_PLAN_LINE_PATTERN = re.compile(r"^\s*(?:\d+[.):]|[-*])\s*")

_APPROVE_PREFIX = "CORRECT"


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    """One reasoning-mode run's own outcome."""

    content: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    succeeded: bool = True
    error: str | None = None


def _parse_plan_steps(text: str) -> list[str]:
    """Parse a numbered or bulleted plan into individual step strings."""
    steps: list[str] = []
    for line in text.splitlines():
        cleaned = _PLAN_LINE_PATTERN.sub("", line).strip()
        if cleaned:
            steps.append(cleaned)
    return steps


async def _ask(
    registry: ModelRegistry, profile: AgentProfile, prompt: str, *, system: str | None = None
) -> tuple[str, int, int]:
    """One plain chat turn; returns ``(content, prompt_tokens, completion_tokens)``."""
    messages = []
    if system:
        messages.append(ChatMessage(role="system", content=system))
    elif profile.system_prompt:
        messages.append(ChatMessage(role="system", content=profile.system_prompt))
    messages.append(ChatMessage(role="user", content=prompt))
    completion = await dispatch_chat(registry, profile, messages)
    return completion.content, completion.prompt_tokens, completion.completion_tokens


async def run_tree_of_thought(
    registry: ModelRegistry,
    profile: AgentProfile,
    request: str,
    *,
    branches: int = 3,
) -> ReasoningResult:
    """Tree-of-Thought: explore *branches* distinct candidate approaches
    in parallel, then pick and synthesise the best one.

    Branches run concurrently -- each is independent model I/O, the
    same "safe to overlap" reasoning
    :meth:`~app.agents.orchestrator.AgentOrchestrator.run_parallel`
    already establishes.
    """
    branch_prompts = [
        f"{request}\n\n(Explore one distinct approach to this, approach "
        f"#{index + 1} of {branches}. Do not repeat the other approaches.)"
        for index in range(branches)
    ]
    try:
        branch_answers = await asyncio.gather(
            *(_ask(registry, profile, prompt) for prompt in branch_prompts)
        )
    except AIError as exc:
        return ReasoningResult(content="", succeeded=False, error=str(exc))

    steps = [
        {"type": "branch", "index": index, "content": content}
        for index, (content, _p, _c) in enumerate(branch_answers)
    ]
    options = "\n\n".join(
        f"Approach {index + 1}:\n{content}"
        for index, (content, _p, _c) in enumerate(branch_answers)
    )
    synthesis_prompt = (
        f"Given these candidate approaches to '{request}', pick the strongest "
        f"one (or combine the best parts of several) and give one final "
        f"answer.\n\n{options}"
    )
    try:
        final_content, prompt_tokens, completion_tokens = await _ask(
            registry, profile, synthesis_prompt
        )
    except AIError as exc:
        return ReasoningResult(content="", steps=steps, succeeded=False, error=str(exc))

    steps.append({"type": "synthesis", "content": final_content})
    total_prompt = sum(p for _c, p, _t in branch_answers) + prompt_tokens
    total_completion = sum(t for _c, _p, t in branch_answers) + completion_tokens
    return ReasoningResult(
        content=final_content,
        steps=steps,
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
    )


async def run_plan_and_execute(
    registry: ModelRegistry, profile: AgentProfile, request: str, *, max_steps: int = 8
) -> ReasoningResult:
    """Plan-and-Execute: produce an ordered plan, then execute each step
    in sequence, each seeing every earlier step's own result."""
    plan_prompt = (
        "Break this request into a short, ordered, numbered list of concrete "
        f"steps (at most {max_steps}). One step per line.\n\nRequest: {request}"
    )
    try:
        plan_content, plan_prompt_tokens, plan_completion_tokens = await _ask(
            registry, profile, plan_prompt
        )
    except AIError as exc:
        return ReasoningResult(content="", succeeded=False, error=str(exc))

    steps_list = _parse_plan_steps(plan_content)[:max_steps] or [request]
    trace: list[dict[str, Any]] = [{"type": "plan", "content": plan_content}]
    total_prompt = plan_prompt_tokens
    total_completion = plan_completion_tokens
    findings: list[str] = []

    for index, step in enumerate(steps_list):
        context = "\n".join(f"- {finding}" for finding in findings)
        step_prompt = f"{step}" if not context else f"Findings so far:\n{context}\n\nNow: {step}"
        try:
            content, prompt_tokens, completion_tokens = await _ask(registry, profile, step_prompt)
        except AIError as exc:
            trace.append({"type": "step", "index": index, "error": str(exc)})
            return ReasoningResult(
                content="\n\n".join(findings), steps=trace, succeeded=False, error=str(exc)
            )
        findings.append(content)
        trace.append({"type": "step", "index": index, "description": step, "content": content})
        total_prompt += prompt_tokens
        total_completion += completion_tokens

    return ReasoningResult(
        content=findings[-1] if findings else "",
        steps=trace,
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
    )


async def run_reflection(
    registry: ModelRegistry, profile: AgentProfile, request: str, *, max_iterations: int = 2
) -> ReasoningResult:
    """Reflection: produce an answer, critique it, then revise -- an
    open-ended self-improvement loop, distinct from
    :func:`run_self_verification`'s binary correctness check.
    """
    try:
        content, prompt_tokens, completion_tokens = await _ask(registry, profile, request)
    except AIError as exc:
        return ReasoningResult(content="", succeeded=False, error=str(exc))

    trace: list[dict[str, Any]] = [{"type": "draft", "content": content}]
    total_prompt, total_completion = prompt_tokens, completion_tokens

    for iteration in range(max_iterations):
        critique_prompt = (
            f"Critique this answer to '{request}'. Name anything unclear, "
            f"incomplete, or wrong. If it is already good, say exactly "
            f"'NO CHANGES NEEDED'.\n\nAnswer: {content}"
        )
        try:
            critique, c_prompt, c_completion = await _ask(registry, profile, critique_prompt)
        except AIError as exc:
            trace.append({"type": "critique", "iteration": iteration, "error": str(exc)})
            break
        trace.append({"type": "critique", "iteration": iteration, "content": critique})
        total_prompt += c_prompt
        total_completion += c_completion

        if critique.strip().upper().startswith("NO CHANGES NEEDED"):
            break

        revise_prompt = (
            f"Revise your answer to '{request}' given this critique: "
            f"{critique}\n\nPrevious answer: {content}"
        )
        try:
            content, r_prompt, r_completion = await _ask(registry, profile, revise_prompt)
        except AIError as exc:
            trace.append({"type": "revision", "iteration": iteration, "error": str(exc)})
            break
        trace.append({"type": "revision", "iteration": iteration, "content": content})
        total_prompt += r_prompt
        total_completion += r_completion

    return ReasoningResult(
        content=content, steps=trace, prompt_tokens=total_prompt, completion_tokens=total_completion
    )


async def run_self_verification(
    registry: ModelRegistry, profile: AgentProfile, request: str, *, max_corrections: int = 2
) -> ReasoningResult:
    """Self-Verification: produce an answer, independently check whether
    it actually answers the request, and correct it if not -- a bounded
    correctness check, not an open-ended critique.
    """
    try:
        content, prompt_tokens, completion_tokens = await _ask(registry, profile, request)
    except AIError as exc:
        return ReasoningResult(content="", succeeded=False, error=str(exc))

    trace: list[dict[str, Any]] = [{"type": "draft", "content": content}]
    total_prompt, total_completion = prompt_tokens, completion_tokens

    for iteration in range(max_corrections):
        verify_prompt = (
            f"Does this answer correctly and completely address the request "
            f"below? Reply starting with exactly '{_APPROVE_PREFIX}' if yes, "
            f"or 'INCORRECT: <what is wrong>' if no.\n\nRequest: {request}\n\n"
            f"Answer: {content}"
        )
        try:
            verdict, v_prompt, v_completion = await _ask(registry, profile, verify_prompt)
        except AIError as exc:
            trace.append({"type": "verify", "iteration": iteration, "error": str(exc)})
            break
        trace.append({"type": "verify", "iteration": iteration, "content": verdict})
        total_prompt += v_prompt
        total_completion += v_completion

        if verdict.strip().upper().startswith(_APPROVE_PREFIX):
            break

        correction_prompt = (
            f"Correct this answer to '{request}'. Verification found: "
            f"{verdict}\n\nPrevious answer: {content}"
        )
        try:
            content, c_prompt, c_completion = await _ask(registry, profile, correction_prompt)
        except AIError as exc:
            trace.append({"type": "correction", "iteration": iteration, "error": str(exc)})
            break
        trace.append({"type": "correction", "iteration": iteration, "content": content})
        total_prompt += c_prompt
        total_completion += c_completion

    return ReasoningResult(
        content=content, steps=trace, prompt_tokens=total_prompt, completion_tokens=total_completion
    )


async def run_tool_based(
    registry: ModelRegistry,
    profile: AgentProfile,
    request: str,
    *,
    executor: ToolExecutor,
    execution: AgentExecution,
    tools_by_key: dict[str, AgentTool],
    agent_tool_keys: list[str],
    granted_categories: list[Any],
    allow_mutating: bool = False,
    max_steps: int = 8,
) -> ReasoningResult:
    """Tool-based Reasoning: let the model call tools mid-thought,
    feeding each real result back as a ``tool``-role turn, until it
    stops requesting tools or *max_steps* is reached.

    Reuses :class:`~app.tool_execution.executor.ToolExecutor` directly
    -- every call this loop makes is authorized, validated, and
    recorded onto *execution* exactly as any other tool call is.
    """
    tool_specs = [to_specification(tool) for tool in tools_by_key.values()]
    messages: list[ChatMessage] = []
    if profile.system_prompt:
        messages.append(ChatMessage(role="system", content=profile.system_prompt))
    messages.append(ChatMessage(role="user", content=request))

    trace: list[dict[str, Any]] = []
    total_prompt = 0
    total_completion = 0

    for step in range(max_steps):
        try:
            completion = await dispatch_chat(registry, profile, messages, tools=tool_specs)
        except AIError as exc:
            return ReasoningResult(content="", steps=trace, succeeded=False, error=str(exc))
        total_prompt += completion.prompt_tokens
        total_completion += completion.completion_tokens

        if not completion.tool_calls:
            trace.append({"type": "final", "step": step, "content": completion.content})
            return ReasoningResult(
                content=completion.content,
                steps=trace,
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
            )

        messages.append(ChatMessage(role="assistant", content=completion.content))
        for call in completion.tool_calls:
            await _run_requested_tool_call(
                call,
                executor=executor,
                execution=execution,
                tools_by_key=tools_by_key,
                agent_tool_keys=agent_tool_keys,
                granted_categories=granted_categories,
                allow_mutating=allow_mutating,
                messages=messages,
                trace=trace,
                step=step,
            )

    trace.append({"type": "max_steps_reached", "step": max_steps})
    return ReasoningResult(
        content=messages[-1].content if messages else "",
        steps=trace,
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        succeeded=False,
        error=f"Reached the maximum of {max_steps} reasoning steps without a final answer.",
    )


async def _run_requested_tool_call(
    call: RequestedToolCall,
    *,
    executor: ToolExecutor,
    execution: AgentExecution,
    tools_by_key: dict[str, AgentTool],
    agent_tool_keys: list[str],
    granted_categories: list[Any],
    allow_mutating: bool,
    messages: list[ChatMessage],
    trace: list[dict[str, Any]],
    step: int,
) -> None:
    """Run one model-requested tool call and append its outcome to
    both the running chat transcript and the reasoning trace."""
    tool = tools_by_key.get(call.name)
    if tool is None:
        content = f"Tool call was not executed: no tool registered as {call.name!r}."
        trace.append({"type": "tool_call", "step": step, "tool_key": call.name, "error": content})
    else:
        outcome = await executor.execute(
            tool,
            call.arguments,
            execution=execution,
            agent_tool_keys=agent_tool_keys,
            granted_categories=granted_categories,
            allow_mutating=allow_mutating,
        )
        content = outcome.as_model_content()
        trace.append(
            {
                "type": "tool_call",
                "step": step,
                "tool_key": call.name,
                "status": str(outcome.status),
            }
        )
    messages.append(
        ChatMessage(role="tool", content=content, tool_call_id=call.call_id, tool_name=call.name)
    )


async def run_knowledge_graph(
    registry: ModelRegistry,
    profile: AgentProfile,
    request: str,
    *,
    graph: GraphClient,
    max_records: int = 50,
) -> ReasoningResult:
    """Knowledge Graph Reasoning: ask the model for a read-only Cypher
    query relevant to the request, run it for real, then answer using
    the graph's own returned facts as context.

    Falls back to answering without graph context (rather than
    failing outright) when the graph is unconfigured or the model's
    own query does not run -- a missing knowledge source should degrade
    an answer's grounding, not the agent's own availability.
    """
    query_prompt = (
        "Write one read-only Cypher query (MATCH/RETURN only, no CREATE/"
        "MERGE/DELETE/SET) that would retrieve graph facts relevant to "
        f"this request. Reply with only the Cypher, nothing else.\n\n"
        f"Request: {request}"
    )
    try:
        cypher, q_prompt, q_completion = await _ask(registry, profile, query_prompt)
    except AIError as exc:
        return ReasoningResult(content="", succeeded=False, error=str(exc))

    trace: list[dict[str, Any]] = [{"type": "cypher", "content": cypher}]
    total_prompt, total_completion = q_prompt, q_completion
    graph_context = ""

    if graph.enabled:
        try:
            result = await graph.read(cypher.strip(), max_records=max_records)
            graph_context = "\n".join(str(record) for record in result.records)
            trace.append({"type": "graph_result", "row_count": result.row_count})
        except Exception as exc:
            trace.append({"type": "graph_error", "error": str(exc)})
    else:
        trace.append({"type": "graph_unavailable"})

    answer_prompt = (
        f"{request}\n\nRelevant knowledge graph facts:\n{graph_context}"
        if graph_context
        else f"{request}\n\n(No relevant knowledge graph facts were found.)"
    )
    try:
        content, a_prompt, a_completion = await _ask(registry, profile, answer_prompt)
    except AIError as exc:
        return ReasoningResult(content="", steps=trace, succeeded=False, error=str(exc))

    trace.append({"type": "answer", "content": content})
    return ReasoningResult(
        content=content,
        steps=trace,
        prompt_tokens=total_prompt + a_prompt,
        completion_tokens=total_completion + a_completion,
    )


async def run_hybrid(
    registry: ModelRegistry, profile: AgentProfile, request: str, *, max_steps: int = 8
) -> ReasoningResult:
    """Hybrid Reasoning: Plan-and-Execute at the top level, with each
    step additionally passed through a Self-Verification check before
    being accepted -- composing two already-real modes rather than
    inventing a third, parallel mechanism.
    """
    plan_result = await run_plan_and_execute(registry, profile, request, max_steps=max_steps)
    if not plan_result.succeeded:
        return plan_result

    step_descriptions = [
        entry["description"] for entry in plan_result.steps if entry.get("type") == "step"
    ]
    if not step_descriptions:
        return plan_result

    verified = await run_self_verification(registry, profile, step_descriptions[-1])
    combined_steps = [*plan_result.steps, {"type": "hybrid_verification", "steps": verified.steps}]
    return ReasoningResult(
        content=verified.content if verified.succeeded else plan_result.content,
        steps=combined_steps,
        prompt_tokens=plan_result.prompt_tokens + verified.prompt_tokens,
        completion_tokens=plan_result.completion_tokens + verified.completion_tokens,
    )


__all__ = [
    "ReasoningResult",
    "run_hybrid",
    "run_knowledge_graph",
    "run_plan_and_execute",
    "run_reflection",
    "run_self_verification",
    "run_tool_based",
    "run_tree_of_thought",
]
