"""Enterprise Exception Framework.

Every custom exception raised anywhere in AI-IOS inherits from
:class:`AIIOSException`; no service defines its own exception hierarchy or
handling mechanism (docs/015_Enterprise_Exception_Framework.md.txt).
"""

from shared_core.exceptions.ai import AIError
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.automation import AutomationError
from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.cache import CacheError
from shared_core.exceptions.configuration import ConfigurationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.connector import ConnectorError
from shared_core.exceptions.constants import (
    ALL_EXCEPTION_CLASSES,
    ERROR_CODE_CATALOG,
    MESSAGE_CATALOG,
    ExceptionConstants,
    localize_message,
)
from shared_core.exceptions.database import DatabaseError
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.event import EventError
from shared_core.exceptions.factory import create_exception, get_exception_class
from shared_core.exceptions.handlers import register_exception_handlers
from shared_core.exceptions.inventory import InventoryError
from shared_core.exceptions.mapper import map_exception
from shared_core.exceptions.monitoring import MonitoringError
from shared_core.exceptions.network import NetworkError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.notification import NotificationError
from shared_core.exceptions.plugin import PluginError
from shared_core.exceptions.queue import QueueError
from shared_core.exceptions.rate_limit import RateLimitError
from shared_core.exceptions.scheduler import SchedulerError
from shared_core.exceptions.service import ExternalError, InternalError, UnknownError
from shared_core.exceptions.storage import StorageError
from shared_core.exceptions.telemetry import TelemetryError
from shared_core.exceptions.timeout import AIIOSTimeoutError
from shared_core.exceptions.validation import ValidationError
from shared_core.exceptions.workflow import WorkflowError

__all__ = [
    "ALL_EXCEPTION_CLASSES",
    "ERROR_CODE_CATALOG",
    "MESSAGE_CATALOG",
    "AIError",
    "AIIOSException",
    "AIIOSTimeoutError",
    "AuthenticationError",
    "AuthorizationError",
    "AutomationError",
    "BusinessRuleError",
    "CacheError",
    "ConfigurationError",
    "ConflictError",
    "ConnectorError",
    "DatabaseError",
    "DependencyError",
    "EventError",
    "ExceptionConstants",
    "ExternalError",
    "InternalError",
    "InventoryError",
    "MonitoringError",
    "NetworkError",
    "NotFoundError",
    "NotificationError",
    "PluginError",
    "QueueError",
    "RateLimitError",
    "SchedulerError",
    "StorageError",
    "TelemetryError",
    "UnknownError",
    "ValidationError",
    "WorkflowError",
    "create_exception",
    "get_exception_class",
    "localize_message",
    "map_exception",
    "register_exception_handlers",
]
