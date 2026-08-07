"""The six named coordination patterns beyond sequential/parallel
(docs/060 "MULTI-AGENT ORCHESTRATION"): Hierarchical Coordination,
Peer-to-peer Collaboration, Supervisor Model, Planner/Executor Pattern,
Agent Delegation, Conflict Resolution.

A genuine gap: nothing in ``ai-assistant-service``'s own precedent
implements these -- only sequential/parallel execution plus keyword
routing exist there. Each function here builds on
:meth:`~app.agents.orchestrator.AgentOrchestrator.run_one`, so every
pattern is a real, additional structure over the same base dispatch --
never a separate model-calling path of its own.
"""

from __future__ import annotations

import re

from app.agents.orchestrator import (
    AgentOrchestrator,
    AgentResult,
    AgentTask,
    SharedMemory,
    aggregate,
    decompose,
)
from app.models.enums import AgentType

_DELEGATION_PATTERN = re.compile(r"DELEGATE_TO:\s*([a-z_]+)\s*\|\s*(.+)", re.IGNORECASE)
_PLAN_LINE_PATTERN = re.compile(r"^\s*(?:\d+[.):]|[-*])\s*")


async def run_hierarchical(
    orchestrator: AgentOrchestrator,
    root_task: AgentTask,
    *,
    coordinator_type: AgentType = AgentType.COORDINATOR,
) -> AgentResult:
    """Hierarchical Coordination: a coordinator decomposes *root_task*
    into sub-tasks, each runs through its own best-fit agent in order,
    and the coordinator then synthesises their results into one answer.
    """
    subtasks = decompose(root_task.description) or [root_task]
    sub_results = await orchestrator.run_sequential(subtasks)

    synthesis_task = AgentTask(
        description=(
            f"Combine these findings into one coherent answer to: "
            f"{root_task.description}\n\n{aggregate(sub_results)}"
        ),
        agent_type=coordinator_type,
    )
    synthesis = await orchestrator.run_one(synthesis_task, SharedMemory())
    if not synthesis.succeeded:
        # The sub-work still happened; report it rather than a bare failure.
        return AgentResult(
            task=root_task,
            agent_name=synthesis.agent_name,
            content=aggregate(sub_results),
            succeeded=any(result.succeeded for result in sub_results),
            error=synthesis.error,
        )
    return synthesis


async def run_peer_to_peer(
    orchestrator: AgentOrchestrator, tasks: list[AgentTask], *, rounds: int = 2
) -> list[AgentResult]:
    """Peer-to-peer Collaboration: independent agents run in rounds,
    each round revising its own answer in light of every other agent's
    most recent one.

    Round 1 is a plain parallel run (agents cannot yet see each other).
    Each subsequent round rewrites every task's own description to
    include the prior round's peer answers, so a revision genuinely
    responds to what peers said rather than repeating round 1.
    """
    if not tasks:
        return []
    results = await orchestrator.run_parallel(tasks)
    for _round_index in range(rounds - 1):
        peer_context = "\n\n".join(
            f"{result.agent_name}: {result.content}" for result in results if result.succeeded
        )
        if not peer_context:
            break
        revised_tasks = [
            AgentTask(
                description=(
                    f"{task.description}\n\nHere is what your peers answered. "
                    f"Revise your own answer if their input changes it, or restate "
                    f"it if not:\n{peer_context}"
                ),
                agent_type=task.agent_type,
                context=task.context,
            )
            for task in tasks
        ]
        results = await orchestrator.run_parallel(revised_tasks)
    return results


async def run_supervised(
    orchestrator: AgentOrchestrator,
    task: AgentTask,
    *,
    supervisor_type: AgentType = AgentType.REVIEWER,
    max_attempts: int = 3,
) -> AgentResult:
    """Supervisor Model: a worker produces an answer, a supervisor
    agent reviews it, and a rejection sends the worker back with the
    supervisor's own feedback attached -- bounded by *max_attempts* so
    a supervisor that never approves cannot loop forever.
    """
    shared = SharedMemory()
    current_task = task
    worker_result = AgentResult(
        task=task, agent_name="none", content="", succeeded=False, error="Never attempted."
    )
    for _attempt in range(max_attempts):
        worker_result = await orchestrator.run_one(current_task, shared)
        if not worker_result.succeeded:
            return worker_result

        review_task = AgentTask(
            description=(
                f"Review this answer to the request below. Reply starting with "
                f"exactly 'APPROVE' or 'REJECT', followed by your reason.\n\n"
                f"Request: {task.description}\n\nAnswer: {worker_result.content}"
            ),
            agent_type=supervisor_type,
        )
        review = await orchestrator.run_one(review_task, shared)
        if not review.succeeded or review.content.strip().upper().startswith("APPROVE"):
            return worker_result

        current_task = AgentTask(
            description=(
                f"{task.description}\n\nYour previous answer was rejected by review: "
                f"{review.content}\nProduce a corrected answer."
            ),
            agent_type=task.agent_type,
            context=task.context,
        )
    return worker_result


def _parse_plan_steps(text: str) -> list[str]:
    """Parse a numbered or bulleted plan into individual step strings."""
    steps: list[str] = []
    for line in text.splitlines():
        cleaned = _PLAN_LINE_PATTERN.sub("", line).strip()
        if cleaned:
            steps.append(cleaned)
    return steps


async def run_planner_executor(
    orchestrator: AgentOrchestrator,
    request: str,
    *,
    planner_type: AgentType = AgentType.PLANNER,
    executor_type: AgentType = AgentType.EXECUTOR,
) -> list[AgentResult]:
    """Planner/Executor Pattern: a planner agent produces an ordered,
    numbered plan; each step then runs through an executor agent in
    sequence, each seeing earlier steps' own findings.
    """
    plan_task = AgentTask(
        description=(
            "Break this request into a short, ordered, numbered list of concrete "
            f"steps. One step per line.\n\nRequest: {request}"
        ),
        agent_type=planner_type,
    )
    plan_result = await orchestrator.run_one(plan_task, SharedMemory())
    if not plan_result.succeeded:
        return [plan_result]

    steps = _parse_plan_steps(plan_result.content)
    executor_tasks = [AgentTask(description=step, agent_type=executor_type) for step in steps] or [
        AgentTask(description=request, agent_type=executor_type)
    ]
    return [plan_result, *await orchestrator.run_sequential(executor_tasks)]


def _parse_delegation(text: str) -> tuple[AgentType, str] | None:
    """Parse a coordinator's own ``DELEGATE_TO: <type> | <description>``
    reply. Returns ``None`` on anything unparseable or naming an unknown
    agent type -- delegation is never forced onto a guess.
    """
    match = _DELEGATION_PATTERN.search(text)
    if not match:
        return None
    try:
        agent_type = AgentType(match.group(1).strip().lower())
    except ValueError:
        return None
    return agent_type, match.group(2).strip()


async def run_delegation(
    orchestrator: AgentOrchestrator,
    task: AgentTask,
    *,
    coordinator_type: AgentType = AgentType.COORDINATOR,
) -> list[AgentResult]:
    """Agent Delegation: a coordinator decides, at run time, which
    specific agent type should take over and with what sub-task --
    rather than the fixed keyword table :func:`~app.agents.orchestrator
    .route` always uses.
    """
    delegation_prompt = (
        f"{task.description}\n\nIf another kind of agent should handle this, "
        f"reply on one line exactly as 'DELEGATE_TO: <agent_type> | <sub-task "
        f"description>', choosing agent_type from: "
        f"{', '.join(str(member) for member in AgentType)}. "
        "Otherwise, just answer the request directly."
    )
    coordinator_result = await orchestrator.run_one(
        AgentTask(description=delegation_prompt, agent_type=coordinator_type), SharedMemory()
    )
    if not coordinator_result.succeeded:
        return [coordinator_result]

    delegated = _parse_delegation(coordinator_result.content)
    if delegated is None:
        return [coordinator_result]

    delegated_type, delegated_description = delegated
    delegated_result = await orchestrator.run_one(
        AgentTask(description=delegated_description, agent_type=delegated_type), SharedMemory()
    )
    return [coordinator_result, delegated_result]


async def run_conflict_resolution(
    orchestrator: AgentOrchestrator,
    results: list[AgentResult],
    original_task: AgentTask,
    *,
    resolver_type: AgentType = AgentType.REVIEWER,
) -> AgentResult:
    """Conflict Resolution: when independent agents (e.g. from
    :func:`run_peer_to_peer` or :meth:`~app.agents.orchestrator
    .AgentOrchestrator.run_parallel`) produce more than one answer, a
    resolver agent reads every one and produces a single reconciled
    answer.

    A single surviving answer needs no resolver call -- there is
    nothing to reconcile.
    """
    succeeded = [result for result in results if result.succeeded]
    if not succeeded:
        if results:
            return results[0]
        return AgentResult(
            task=original_task,
            agent_name="none",
            content="",
            succeeded=False,
            error="No results to resolve.",
        )
    if len(succeeded) == 1:
        return succeeded[0]

    options = "\n\n".join(
        f"Option from {result.agent_name}:\n{result.content}" for result in succeeded
    )
    resolution_task = AgentTask(
        description=(
            f"These agents disagree while answering: {original_task.description}\n\n"
            f"{options}\n\nProduce one single reconciled answer."
        ),
        agent_type=resolver_type,
    )
    return await orchestrator.run_one(resolution_task, SharedMemory())


__all__ = [
    "run_conflict_resolution",
    "run_delegation",
    "run_hierarchical",
    "run_peer_to_peer",
    "run_planner_executor",
    "run_supervised",
]
