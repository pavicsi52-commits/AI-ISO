"""Validation result model returned by every validator in this package."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of running a single validator.

    Attributes:
        valid: Whether the value passed validation.
        errors: Human-readable validation error messages. Empty if valid.
        warnings: Non-fatal issues worth surfacing even when valid.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, warnings: list[str] | None = None) -> ValidationResult:
        """Build a successful result, optionally carrying warnings."""
        return cls(valid=True, errors=[], warnings=warnings or [])

    @classmethod
    def fail(cls, *errors: str) -> ValidationResult:
        """Build a failed result with one or more error messages."""
        return cls(valid=False, errors=list(errors), warnings=[])
