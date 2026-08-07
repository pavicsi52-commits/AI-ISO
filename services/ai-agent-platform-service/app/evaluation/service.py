"""Evaluates one agent execution and persists the result (docs/060
"EVALUATION").
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.clients.registry import ModelRegistry
from app.evaluation.scoring import (
    score_execution_quality,
    score_reasoning_efficiency,
    score_task_accuracy_lexical,
    score_task_accuracy_with_model,
    score_tool_success_rate,
)
from app.models.evaluation import AgentEvaluation
from app.models.execution import AgentExecution
from app.models.profile import AgentProfile
from app.repositories.evaluation import AgentEvaluationRepository


class EvaluationService:
    """Scores one execution across every docs/060 "EVALUATION" metric
    and records the result."""

    def __init__(self, evaluations: AgentEvaluationRepository) -> None:
        self._evaluations = evaluations

    async def evaluate_execution(
        self,
        execution: AgentExecution,
        *,
        max_reasoning_steps: int = 8,
        expected_output: str | None = None,
        registry: ModelRegistry | None = None,
        judge_profile: AgentProfile | None = None,
        human_feedback_score: float | None = None,
        is_regression_test: bool = False,
        evaluated_by: str | None = None,
    ) -> AgentEvaluation:
        """Score *execution* and persist an :class:`AgentEvaluation`.

        Task accuracy is only computed when *expected_output* is
        given -- there is no ground truth to compare against
        otherwise. It uses the real model judge
        (:func:`~app.evaluation.scoring.score_task_accuracy_with_model`)
        when both *registry* and *judge_profile* are supplied, falling
        back to the deterministic lexical scorer otherwise.
        """
        task_accuracy: float | None = None
        if expected_output is not None:
            actual = execution.output_summary or ""
            if registry is not None and judge_profile is not None:
                task_accuracy = await score_task_accuracy_with_model(
                    registry,
                    judge_profile,
                    request=execution.input_summary or "",
                    actual=actual,
                    expected=expected_output,
                )
            else:
                task_accuracy = score_task_accuracy_lexical(actual, expected_output)

        return await self._evaluations.create(
            AgentEvaluation(
                organization_id=execution.organization_id,
                agent_id=execution.agent_id,
                execution_id=execution.id,
                task_accuracy=task_accuracy,
                execution_quality=score_execution_quality(execution),
                reasoning_quality=score_reasoning_efficiency(
                    execution, max_reasoning_steps=max_reasoning_steps
                ),
                tool_success_rate=score_tool_success_rate(execution),
                latency_ms=execution.latency_ms,
                cost_usd=execution.cost_usd,
                human_feedback_score=human_feedback_score,
                is_regression_test=is_regression_test,
                evaluated_by=evaluated_by,
                evaluated_at=datetime.now(UTC),
            )
        )


__all__ = ["EvaluationService"]
