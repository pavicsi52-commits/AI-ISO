"""Validation rules, grouped by category.

Each submodule corresponds to one docs/016_Enterprise_Validation_Framework.md.txt
category (``field``, ``request``, ``response``, ``business``, ``database``,
``security``, ``workflow``, ``connectors``) and is a plain namespace of
functions -- rules are looked up and executed by
:class:`shared_core.validation.manager.ValidationManager`, not called
directly through this package in most cases, though every function here
is a perfectly normal, directly-callable function too.
"""

from __future__ import annotations

from shared_core.validation.rules import (
    business,
    connectors,
    database,
    field,
    request,
    response,
    security,
    workflow,
)

__all__ = [
    "business",
    "connectors",
    "database",
    "field",
    "request",
    "response",
    "security",
    "workflow",
]
