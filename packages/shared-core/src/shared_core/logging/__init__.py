"""Enterprise Logging Framework.

Every service uses this instead of ``print()`` or a locally configured
logger (docs/014_Enterprise_Logging_Framework.md.txt).
"""

from shared_core.logging.config import LoggingConfig, build_logging_config
from shared_core.logging.constants import LoggingFrameworkConstants
from shared_core.logging.context import (
    LogContext,
    bind_log_context,
    get_log_context,
    reset_log_context,
)
from shared_core.logging.exceptions import LoggingConfigurationError, LogHandlerError
from shared_core.logging.factory import (
    configure_logging_from_config,
    configure_logging_from_settings,
)
from shared_core.logging.filters import SensitiveDataFilter, mask_payload, mask_text, mask_value
from shared_core.logging.formatter import build_log_record
from shared_core.logging.handlers import (
    build_console_handler,
    build_file_handler,
    build_otel_handler,
)
from shared_core.logging.json_formatter import JsonFormatter
from shared_core.logging.logger import AIIOSLogger, configure_logging, get_logger, resolve_log_level
from shared_core.logging.middleware import RequestLoggingMiddleware
from shared_core.logging.request_context import (
    RequestLogContext,
    bind_request_log_context,
    get_request_log_context,
    reset_request_log_context,
)
from shared_core.logging.retention import cleanup_old_logs
from shared_core.logging.rotation import SizeAndTimeRotatingHandler

__all__ = [
    "AIIOSLogger",
    "JsonFormatter",
    "LogContext",
    "LogHandlerError",
    "LoggingConfig",
    "LoggingConfigurationError",
    "LoggingFrameworkConstants",
    "RequestLogContext",
    "RequestLoggingMiddleware",
    "SensitiveDataFilter",
    "SizeAndTimeRotatingHandler",
    "bind_log_context",
    "bind_request_log_context",
    "build_console_handler",
    "build_file_handler",
    "build_log_record",
    "build_logging_config",
    "build_otel_handler",
    "cleanup_old_logs",
    "configure_logging",
    "configure_logging_from_config",
    "configure_logging_from_settings",
    "get_log_context",
    "get_logger",
    "get_request_log_context",
    "mask_payload",
    "mask_text",
    "mask_value",
    "reset_log_context",
    "reset_request_log_context",
    "resolve_log_level",
]
