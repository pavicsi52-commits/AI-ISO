"""Validation pipeline: runs layers in the required order, stopping at the first failure.

Per docs/016_Enterprise_Validation_Framework.md.txt "PIPELINE": Input ->
Sanitize -> Validate -> Business Rules -> Permissions -> Database Rules ->
Success or Structured Error. "No validation layer may be skipped" is
enforced here: a caller may run any *subset* of layers, but never out of
their relative order.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from shared_core.validation.base import ValidationLayer
from shared_core.validation.constants import ValidationFrameworkConstants
from shared_core.validation.exceptions import ValidationPipelineError
from shared_core.validation.manager import ValidationManager, default_manager
from shared_core.validation.results import PipelineResult


@dataclass(frozen=True, slots=True)
class LayerStep:
    """One step in a pipeline run: which registered validator to run, and its arguments."""

    layer: ValidationLayer
    name: str
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)


class ValidationPipeline:
    """Executes an ordered sequence of validation steps, layer by layer."""

    def __init__(self, manager: ValidationManager | None = None) -> None:
        self._manager = manager or default_manager

    def run(self, steps: Sequence[LayerStep]) -> PipelineResult:
        """Run *steps* in order, stopping at the first failing layer.

        Raises:
            ValidationPipelineError: If *steps* are out of the required
                layer order (docs/016 "No validation layer may be skipped").
        """
        _assert_ordered(steps)

        start = time.perf_counter()
        layer_results = {}
        for step in steps:
            result = self._manager.run(step.layer, step.name, *step.args, **step.kwargs)
            layer_results[step.layer.value] = result
            if not result.valid:
                return PipelineResult(
                    valid=False,
                    layer_results=layer_results,
                    failed_layer=step.layer.value,
                    total_execution_time_ms=(time.perf_counter() - start) * 1000,
                )

        return PipelineResult(
            valid=True,
            layer_results=layer_results,
            failed_layer=None,
            total_execution_time_ms=(time.perf_counter() - start) * 1000,
        )


def _assert_ordered(steps: Sequence[LayerStep]) -> None:
    order = ValidationFrameworkConstants.LAYER_ORDER
    last_index = -1
    for step in steps:
        index = order.index(step.layer.value)
        if index < last_index:
            raise ValidationPipelineError(
                f"Validation steps out of order: layer '{step.layer.value}' "
                f"was scheduled after a later layer."
            )
        last_index = index
