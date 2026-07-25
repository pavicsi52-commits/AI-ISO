"""Validator interface.

Concrete implementations live in ``shared_core.validators``
(docs/016_Enterprise_Validation_Framework.md.txt).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared_core.validators.results import ValidationResult


@runtime_checkable
class ValidatorProtocol[ValueT](Protocol):
    """Structural interface for a single-value validator."""

    def validate(self, value: ValueT) -> ValidationResult:
        """Validate the given value and return a structured result."""
        ...
