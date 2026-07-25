"""Validation-framework-local constants.

Distinct from :class:`shared_core.constants.validation.ValidationConstants`
(field length/pattern constants the individual field validators use) --
these govern the pipeline's own mechanics: layer order and performance
budgets.
"""

from __future__ import annotations

from typing import Final


class ValidationFrameworkConstants:
    """Constants governing the validation pipeline itself."""

    # docs/016_Enterprise_Validation_Framework.md.txt "VALIDATION LAYERS",
    # in required execution order. "No validation layer may be skipped"
    # means the pipeline never reorders or interleaves these -- a caller
    # may run a subset, but always in this relative order.
    LAYER_ORDER: Final[tuple[str, ...]] = (
        "environment",
        "configuration",
        "api",
        "schema",
        "business",
        "database",
        "permission",
        "workflow",
        "response",
    )

    # docs/016 "PERFORMANCE"
    MAX_PIPELINE_LATENCY_MS: Final[float] = 10.0
    MAX_FIELD_VALIDATION_LATENCY_MS: Final[float] = 1.0
