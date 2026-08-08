"""Service layer: wraps repositories and pure engines into the API
surface docs/060's own "REST APIs" section names."""

from __future__ import annotations

from app.services.agent import AgentService, ProfileFields
from app.services.execution import ExecutionService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.task import TaskService
from app.services.tool import ToolService
from app.services.tool_handlers import HandlerDependencies, build_handler_registry

__all__ = [
    "AgentService",
    "AuditService",
    "ExecutionService",
    "HandlerDependencies",
    "ProfileFields",
    "ReportService",
    "StatisticsService",
    "TaskService",
    "ToolService",
    "build_handler_registry",
]
