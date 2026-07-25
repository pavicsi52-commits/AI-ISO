"""Parallel execution.

Per docs/028_Enterprise_Workflow_SDK.md.txt "EXECUTION MODES": Parallel;
"PERFORMANCE": Parallel Workers. Runs a ``PARALLEL`` node's branches
concurrently, bounded by ``max_concurrency``, collecting every branch's
outcome (value or exception) rather than cancelling siblings on the
first failure -- what "all branches succeeded" vs. "any branch failed"
means is a ``MERGE`` node's policy decision, not this module's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shared_core.workflow.constants import DEFAULT_MAX_PARALLEL_BRANCHES


@dataclass(frozen=True, slots=True)
class BranchResult[T]:
    """One parallel branch's outcome."""

    branch_id: str
    succeeded: bool
    value: T | None = None
    error: BaseException | None = None


async def run_parallel[T](
    branches: dict[str, Callable[[], Awaitable[T]]],
    *,
    max_concurrency: int = DEFAULT_MAX_PARALLEL_BRANCHES,
) -> list[BranchResult[T]]:
    """Run every branch in *branches* concurrently, bounded by *max_concurrency* ("Parallel")."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(branch_id: str, branch: Callable[[], Awaitable[T]]) -> BranchResult[T]:
        async with semaphore:
            try:
                value = await branch()
            except Exception as exc:
                return BranchResult(branch_id=branch_id, succeeded=False, error=exc)
            return BranchResult(branch_id=branch_id, succeeded=True, value=value)

    return await asyncio.gather(
        *(_run_one(branch_id, branch) for branch_id, branch in branches.items())
    )


__all__ = ["BranchResult", "run_parallel"]
