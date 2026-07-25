"""Validator adapter: wraps a raw rule callable with timing and naming.

Every rule function under ``shared_core.validation.rules`` returns a bare
:class:`~shared_core.validation.results.ValidationResult` with no timing
or name attached; this is what fills in "Execution Time" and "Validator
Name" (docs/016 "RESULT MODEL") without every individual rule function
needing to do its own timing bookkeeping --
"No validation logic shall be duplicated".
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from shared_core.validation.results import ValidationResult


@dataclass(frozen=True, slots=True)
class Validator:
    """A named, timed wrapper around a raw validation rule function."""

    name: str
    func: Callable[..., ValidationResult]
    layer: str = ""

    def run(self, *args: Any, **kwargs: Any) -> ValidationResult:
        """Execute the wrapped rule, attaching timing and its name to the result."""
        start = time.perf_counter()
        result = self.func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return replace(result, execution_time_ms=elapsed_ms, validator_name=self.name)
