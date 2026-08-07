"""Tool registry: what a tool is and whether one call may run (docs/060 "TOOL REGISTRY")."""

from __future__ import annotations

from app.tool_registry.registry import (
    ALLOWED,
    AuthorizationDecision,
    ToolHandler,
    ToolHandlerRegistry,
    authorize,
    to_specification,
    validate_arguments,
)

__all__ = [
    "ALLOWED",
    "AuthorizationDecision",
    "ToolHandler",
    "ToolHandlerRegistry",
    "authorize",
    "to_specification",
    "validate_arguments",
]
