"""Connector-SDK-specific exceptions.

Each subclasses :class:`shared_core.exceptions.connector.ConnectorError`
so a bare ``except ConnectorError`` still catches everything raised
anywhere in this SDK. Not registered in
:mod:`shared_core.exceptions.constants`'s central catalog -- same
reasoning as every other Prompt 018-026 framework: that module would
need to import from here, and this module already imports from
``shared_core.exceptions.connector``, so a back-import would cycle.
Error codes are manually kept unique in the ``AIIOS-CONNECTOR-*`` range
against the base class's ``AIIOS-CONNECTOR-0001``.
"""

from __future__ import annotations

from shared_core.exceptions.connector import ConnectorError


class ConnectionFailedError(ConnectorError):
    """Raised when establishing a connection to a target fails."""

    error_code = "AIIOS-CONNECTOR-0002"
    status_code = 502
    retryable = True
    default_user_message = "Could not connect to the target."


class AuthenticationFailedError(ConnectorError):
    """Raised when a connector fails to authenticate against its target."""

    error_code = "AIIOS-CONNECTOR-0003"
    status_code = 401
    retryable = False
    default_user_message = "Authentication to the target failed."


class SessionExpiredError(ConnectorError):
    """Raised when an operation is attempted on an expired or terminated session."""

    error_code = "AIIOS-CONNECTOR-0004"
    status_code = 401
    retryable = True
    default_user_message = "The connector session has expired."


class DiscoveryFailedError(ConnectorError):
    """Raised when host/service/port/resource/capability discovery fails."""

    error_code = "AIIOS-CONNECTOR-0005"
    status_code = 502
    retryable = True
    default_user_message = "Discovery could not be completed."


class InventoryCollectionError(ConnectorError):
    """Raised when collecting inventory from a target fails."""

    error_code = "AIIOS-CONNECTOR-0006"
    status_code = 502
    retryable = True
    default_user_message = "Inventory collection could not be completed."


class ConnectorValidationError(ConnectorError):
    """Raised when a connection, credential, certificate, or capability check fails."""

    error_code = "AIIOS-CONNECTOR-0007"
    status_code = 422
    retryable = False
    default_user_message = "The connector configuration is invalid."


class CommandExecutionError(ConnectorError):
    """Raised when executing a command against a target fails."""

    error_code = "AIIOS-CONNECTOR-0008"
    status_code = 502
    retryable = True
    default_user_message = "The command could not be executed."


class FileTransferError(ConnectorError):
    """Raised when an upload or download fails."""

    error_code = "AIIOS-CONNECTOR-0009"
    status_code = 502
    retryable = True
    default_user_message = "The file transfer failed."


class ConnectorTimeoutError(ConnectorError):
    """Raised when a connector operation exceeds its configured timeout."""

    error_code = "AIIOS-CONNECTOR-0010"
    status_code = 504
    retryable = True
    default_user_message = "The connector operation timed out."


class ConnectorRateLimitExceededError(ConnectorError):
    """Raised when a caller exceeds the configured rate limit for a connector/target."""

    error_code = "AIIOS-CONNECTOR-0011"
    status_code = 429
    retryable = True
    default_user_message = "Too many requests to this connector. Please slow down."


class CircuitBreakerOpenError(ConnectorError):
    """Raised when a call is rejected because the target's circuit breaker is open."""

    error_code = "AIIOS-CONNECTOR-0012"
    status_code = 503
    retryable = True
    default_user_message = "This connector is temporarily unavailable. Please try again later."


class CapabilityNotSupportedError(ConnectorError):
    """Raised when an operation isn't supported by a connector's declared capabilities."""

    error_code = "AIIOS-CONNECTOR-0013"
    status_code = 501
    retryable = False
    default_user_message = "This operation is not supported by the target."


class ProviderNotRegisteredError(ConnectorError):
    """Raised when a requested provider has no registered connector class."""

    error_code = "AIIOS-CONNECTOR-0014"
    status_code = 404
    retryable = False
    default_user_message = "The requested connector provider is not available."


__all__ = [
    "AuthenticationFailedError",
    "CapabilityNotSupportedError",
    "CircuitBreakerOpenError",
    "CommandExecutionError",
    "ConnectionFailedError",
    "ConnectorRateLimitExceededError",
    "ConnectorTimeoutError",
    "ConnectorValidationError",
    "DiscoveryFailedError",
    "FileTransferError",
    "InventoryCollectionError",
    "ProviderNotRegisteredError",
    "SessionExpiredError",
]
