"""Workflow templates.

Per docs/028_Enterprise_Workflow_SDK.md.txt "OBJECTIVE": Workflow
Templates. A :class:`WorkflowTemplate` wraps a raw (not-yet-parsed)
workflow definition structure plus declared parameters with defaults;
:meth:`WorkflowTemplate.instantiate` substitutes ``${parameter}``
placeholders (stdlib :class:`string.Template`, since this is simple
value substitution, not the full expression language
:mod:`shared_core.workflow.expressions` provides for conditions) and
hands the result to :func:`shared_core.workflow.parser.parse_dict`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from string import Template
from typing import Any

from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.exceptions import InvalidWorkflowDefinitionError
from shared_core.workflow.parser import parse_dict


def _substitute(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return Template(value).substitute(values)
    if isinstance(value, dict):
        return {key: _substitute(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, values) for item in value]
    return copy.deepcopy(value)


@dataclass(frozen=True, slots=True)
class WorkflowTemplate:
    """A reusable, parameterizable workflow definition."""

    template_id: str
    structure: dict[str, Any]
    parameters: dict[str, Any] = field(default_factory=dict)

    def instantiate(self, **overrides: Any) -> WorkflowDefinition:
        """Fill in ``${parameter}`` placeholders and parse the result into a ``WorkflowDefinition``.

        Raises:
            InvalidWorkflowDefinitionError: If a placeholder has no
                matching parameter (default or override), or the
                resulting structure is otherwise malformed.
        """
        values = {**self.parameters, **overrides}
        try:
            substituted = _substitute(self.structure, values)
        except KeyError as exc:
            raise InvalidWorkflowDefinitionError(
                f"Template {self.template_id!r} references undeclared parameter {exc}."
            ) from exc
        return parse_dict(substituted)


__all__ = ["WorkflowTemplate"]
