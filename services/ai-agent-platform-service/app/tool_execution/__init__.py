"""Tool execution: authorize, validate, execute, record (docs/060 "TOOL EXECUTION")."""

from __future__ import annotations

from app.tool_execution.executor import ToolCallOutcome, ToolExecutor
from app.tool_execution.handlers import (
    MAX_DATABASE_QUERY_ROWS,
    build_automation_handler,
    build_database_query_handler,
    build_knowledge_graph_query_handler,
    build_python_handler,
    build_rest_handler,
    build_shell_handler,
    build_webhook_handler,
    build_workflow_handler,
)

__all__ = [
    "MAX_DATABASE_QUERY_ROWS",
    "ToolCallOutcome",
    "ToolExecutor",
    "build_automation_handler",
    "build_database_query_handler",
    "build_knowledge_graph_query_handler",
    "build_python_handler",
    "build_rest_handler",
    "build_shell_handler",
    "build_webhook_handler",
    "build_workflow_handler",
]
