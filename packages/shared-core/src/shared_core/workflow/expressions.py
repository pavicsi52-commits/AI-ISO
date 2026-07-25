"""Expression evaluation.

Per docs/028_Enterprise_Workflow_SDK.md.txt "CONDITIONS": Expression,
Variable Evaluation. Reuses Jinja2's
``SandboxedEnvironment.compile_expression()`` (the same sandboxing
already vetted for template rendering in Prompt 025's
:mod:`shared_core.notifications.renderer`) rather than ``eval()`` or a
hand-rolled AST walker -- a condition expression may come from a
workflow definition a user authored (YAML/JSON), not just trusted
source code, so unrestricted evaluation would be a real injection risk.
"""

from __future__ import annotations

from typing import Any

from jinja2.sandbox import SandboxedEnvironment

from shared_core.workflow.exceptions import ExpressionEvaluationError

_environment = SandboxedEnvironment()


def evaluate_expression(expression: str, variables: dict[str, Any]) -> Any:
    """Evaluate *expression* against *variables* and return its value ("Expression").

    Any failure -- a malformed expression, a sandbox violation, or a
    genuine runtime error in the expression itself (e.g. dividing by a
    variable that's zero) -- is funneled into this SDK's own typed
    exception, since a user-authored expression's failure is always
    "expression evaluation failed" regardless of the underlying cause.

    Raises:
        ExpressionEvaluationError: If evaluation fails for any reason.
    """
    try:
        compiled = _environment.compile_expression(expression)
        return compiled(**variables)
    except Exception as exc:
        raise ExpressionEvaluationError(f"Failed to evaluate {expression!r}: {exc}") from exc


def evaluate_condition(expression: str, variables: dict[str, Any]) -> bool:
    """Evaluate *expression* and coerce its result to a boolean ("Variable Evaluation")."""
    return bool(evaluate_expression(expression, variables))


__all__ = ["evaluate_condition", "evaluate_expression"]
