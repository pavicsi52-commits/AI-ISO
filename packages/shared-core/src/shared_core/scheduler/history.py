"""Execution history.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "HISTORY": Track
Execution Time, Duration, Result, Retries, Errors, Worker, Status.
Purely in-process, bounded to ``max_entries`` -- the same
"purely in-process" pattern as
:class:`shared_core.telemetry.analytics.TraceRecorder`; persistence
across restarts is a concern for whatever repository layer wraps this
in a running service. "Logs"/"Output" aren't modeled as separate
fields: a job's ``fn`` (per :data:`shared_core.scheduler.job.JobFn`)
returns nothing and produces no output channel this framework defines
-- a job's own logging already goes through
:mod:`shared_core.logging`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from shared_core.scheduler.constants import DEFAULT_HISTORY_BUFFER_SIZE
from shared_core.scheduler.executor import ExecutionResult


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One recorded job execution."""

    job_id: str
    worker_node_id: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    succeeded: bool
    attempts: int
    error: str | None = None

    @property
    def status(self) -> str:
        """``"succeeded"`` or ``"failed"`` ("Status")."""
        return "succeeded" if self.succeeded else "failed"


class HistoryStore:
    """A bounded, in-process record of recent job executions."""

    def __init__(self, *, max_entries: int = DEFAULT_HISTORY_BUFFER_SIZE) -> None:
        self._entries: deque[HistoryEntry] = deque(maxlen=max_entries)

    def record(self, worker_node_id: str, result: ExecutionResult) -> HistoryEntry:
        """Record one execution's outcome ("Track")."""
        entry = HistoryEntry(
            job_id=result.job_id,
            worker_node_id=worker_node_id,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_seconds=result.duration_seconds,
            succeeded=result.succeeded,
            attempts=result.attempts,
            error=result.error,
        )
        self._entries.append(entry)
        return entry

    def for_job(self, job_id: str) -> list[HistoryEntry]:
        """Every recorded execution of *job_id*, oldest first."""
        return [entry for entry in self._entries if entry.job_id == job_id]

    def recent(self, limit: int | None = None) -> list[HistoryEntry]:
        """The most recent executions across every job, newest first."""
        entries = list(reversed(self._entries))
        return entries[:limit] if limit is not None else entries

    def failure_count(self, job_id: str) -> int:
        """How many of *job_id*'s recorded executions failed ("Retries")."""
        return sum(1 for entry in self.for_job(job_id) if not entry.succeeded)


__all__ = ["HistoryEntry", "HistoryStore"]
