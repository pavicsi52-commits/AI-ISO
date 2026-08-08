"""``prompt_tests``, ``prompt_test_results``, ``prompt_ab_tests``, and
``prompt_executions``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    AbTestArm,
    AbTestStatus,
    ExecutionStatus,
    TestKind,
    TestRunStatus,
)


class PromptTest(BaseModel):
    """``prompt_tests`` -- one reusable test definition for a prompt.

    Attaches to the prompt *identity*, not a version: the point of a
    regression test is that it outlives any single revision and is
    re-run against each new one.
    """

    __tablename__ = "prompt_tests"
    __table_args__ = (
        Index("ix_prompt_test_kind", "kind"),
        Index("ix_prompt_test_status", "last_status"),
    )

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[TestKind] = mapped_column(String(24), default=TestKind.AUTOMATED, index=True)
    variables: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """The variable set this case renders the prompt with."""
    expected_output: Mapped[str | None] = mapped_column(Text, default=None)
    expected_substrings: Mapped[list[str]] = mapped_column(JSON, default=list)
    """A looser assertion than exact equality, which is almost never
    the right check against a generative model."""
    forbidden_substrings: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_score: Mapped[float] = mapped_column(Float, default=0.7)
    snapshot: Mapped[str | None] = mapped_column(Text, default=None)
    """ "Snapshot Testing" -- the previously accepted rendered output,
    compared against on each run."""
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[TestRunStatus] = mapped_column(
        String(16), default=TestRunStatus.PENDING, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PromptTestResult(BaseModel):
    """``prompt_test_results`` -- one execution of one test definition.

    Records the *version* it ran against, which is what makes
    regression testing meaningful: the same test's history across
    revisions is the regression signal.
    """

    __tablename__ = "prompt_test_results"
    __table_args__ = (
        Index("ix_prompt_test_result_status", "status"),
        Index("ix_prompt_test_result_run_at", "run_at"),
    )

    prompt_test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_tests.id", ondelete="CASCADE"), index=True
    )
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[TestRunStatus] = mapped_column(
        String(16), default=TestRunStatus.PENDING, index=True
    )
    score: Mapped[float | None] = mapped_column(Float, default=None)
    rendered_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    actual_output: Mapped[str | None] = mapped_column(Text, default=None)
    failure_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    run_by: Mapped[str | None] = mapped_column(String(128), default=None)


class PromptAbTest(BaseModel):
    """``prompt_ab_tests`` -- one traffic-split experiment between two
    revisions of the same prompt.

    Control and variant are both :class:`~app.models.prompt.PromptVersion`
    ids of the same prompt. Counters are kept on the row rather than
    recomputed from ``prompt_executions`` on every read: a winner
    decision runs on a schedule and must not require a full table scan
    of every execution to reach a verdict.
    """

    __tablename__ = "prompt_ab_tests"
    __table_args__ = (Index("ix_prompt_ab_test_status", "status"),)

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[AbTestStatus] = mapped_column(String(16), default=AbTestStatus.DRAFT, index=True)
    control_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE")
    )
    variant_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE")
    )
    variant_weight: Mapped[float] = mapped_column(Float, default=0.5)
    """ "Weighted Distribution" -- the share of traffic routed to the
    variant, in ``[0, 1]``."""
    minimum_samples_per_arm: Mapped[int] = mapped_column(Integer, default=100)
    significance_level: Mapped[float] = mapped_column(Float, default=0.05)
    control_executions: Mapped[int] = mapped_column(Integer, default=0)
    control_successes: Mapped[int] = mapped_column(Integer, default=0)
    variant_executions: Mapped[int] = mapped_column(Integer, default=0)
    variant_successes: Mapped[int] = mapped_column(Integer, default=0)
    winner: Mapped[AbTestArm | None] = mapped_column(String(16), default=None)
    p_value: Mapped[float | None] = mapped_column(Float, default=None)
    is_significant: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_promote: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_notes: Mapped[str | None] = mapped_column(Text, default=None)


class PromptExecution(BaseModel):
    """``prompt_executions`` -- one recorded use of a prompt in production.

    Written by whichever service actually called the model
    (ai-assistant-service, ai-agent-platform-service), not by this
    service: this service governs prompts, it does not execute them.
    That is why there is no provider credential anywhere in this
    codebase.

    ``rendered_prompt`` is stored **masked** -- any variable declared
    ``is_masked`` or resolved from a secret reference is replaced
    before the row is written.
    """

    __tablename__ = "prompt_executions"
    __table_args__ = (
        Index("ix_prompt_execution_status", "status"),
        Index("ix_prompt_execution_executed_at", "executed_at"),
        Index("ix_prompt_execution_version", "prompt_version_id"),
    )

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True
    )
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    ab_test_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_ab_tests.id", ondelete="SET NULL"), default=None, index=True
    )
    ab_arm: Mapped[AbTestArm | None] = mapped_column(String(16), default=None)
    status: Mapped[ExecutionStatus] = mapped_column(
        String(16), default=ExecutionStatus.SUCCEEDED, index=True
    )
    model_provider: Mapped[str | None] = mapped_column(String(32), default=None)
    model_name: Mapped[str | None] = mapped_column(String(128), default=None)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    rendered_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    result_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    executed_by: Mapped[str | None] = mapped_column(String(128), default=None)
    agent_id: Mapped[str | None] = mapped_column(String(128), default=None)
    workflow_id: Mapped[str | None] = mapped_column(String(128), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PromptAbTest", "PromptExecution", "PromptTest", "PromptTestResult"]
