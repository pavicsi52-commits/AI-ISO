"""Validation result models.

Per docs/016_Enterprise_Validation_Framework.md.txt "RESULT MODEL": every
validation returns Valid, Errors, Warnings, Suggestions, Execution Time,
Validator Name, and Severity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared_core.validation.base import ValidationSeverity


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of running a single validator or rule."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    validator_name: str = ""
    severity: ValidationSeverity = ValidationSeverity.ERROR

    @classmethod
    def ok(
        cls,
        *,
        warnings: list[str] | None = None,
        suggestions: list[str] | None = None,
        validator_name: str = "",
        execution_time_ms: float = 0.0,
    ) -> ValidationResult:
        """Build a successful result, optionally carrying warnings/suggestions."""
        return cls(
            valid=True,
            errors=[],
            warnings=warnings or [],
            suggestions=suggestions or [],
            execution_time_ms=execution_time_ms,
            validator_name=validator_name,
            severity=ValidationSeverity.INFO,
        )

    @classmethod
    def fail(
        cls,
        *errors: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        suggestions: list[str] | None = None,
        validator_name: str = "",
        execution_time_ms: float = 0.0,
    ) -> ValidationResult:
        """Build a failed result with one or more error messages."""
        return cls(
            valid=False,
            errors=list(errors),
            warnings=[],
            suggestions=suggestions or [],
            execution_time_ms=execution_time_ms,
            validator_name=validator_name,
            severity=severity,
        )


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Aggregate outcome of running a :class:`~shared_core.validation.pipeline.ValidationPipeline`.

    Per docs/016 "PIPELINE": the pipeline runs layers in order and stops
    at the first failure, so ``layer_results`` only ever contains the
    layers that actually ran.
    """

    valid: bool
    layer_results: dict[str, ValidationResult] = field(default_factory=dict)
    failed_layer: str | None = None
    total_execution_time_ms: float = 0.0

    @property
    def errors(self) -> list[str]:
        """Every error message across every layer that ran."""
        return [error for result in self.layer_results.values() for error in result.errors]

    @property
    def warnings(self) -> list[str]:
        """Every warning message across every layer that ran."""
        return [warning for result in self.layer_results.values() for warning in result.warnings]
