"""Enterprise Connector SDK.

Per docs/027_Enterprise_Connector_SDK.md.txt. A unified SDK for
connecting to infrastructure, operating systems, cloud providers,
virtualization platforms, industrial devices, storage systems,
networking equipment, APIs, and enterprise applications: connection
management, authentication, session management, discovery, command
execution, inventory collection, validation, health monitoring, retry,
rate limiting, audit, telemetry, metrics, and plugin support.

This package ships the reusable core SDK only --
:class:`~shared_core.connectors.base.BaseConnector` and everything
around it. Concrete provider packages (SSH, WinRM, Redfish, SNMP, IPMI,
Docker, Kubernetes, VMware, Proxmox, Hyper-V, OPC UA, Modbus, BACnet,
MQTT, REST, GraphQL, gRPC, SFTP, FTP, SMB, LDAP, Active Directory, DNS,
NTP, AWS, Azure, GCP) are each a separate, later phase of work under
``shared_core.connectors.providers.*`` -- none are implemented in this
package yet; a caller registers whatever providers it needs into a
:class:`~shared_core.connectors.registry.ConnectorRegistry` itself
(directly, or via ``@connector(provider_name)``) and this SDK handles
everything else identically regardless of provider.
"""

from __future__ import annotations

from shared_core.connectors.audit import (
    audit_authenticate,
    audit_command,
    audit_connect,
    audit_disconnect,
    audit_discovery,
    audit_failure,
    audit_inventory,
    audit_transfer,
)
from shared_core.connectors.authentication import AuthenticationResult, Authenticator, authenticate
from shared_core.connectors.base import (
    BaseConnector,
    CommandResult,
    ConnectorCapability,
    ConnectorMetricsSnapshot,
)
from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import (
    Credential,
    CredentialType,
    api_key,
    bearer_token,
    certificate,
    jwt_credential,
    oauth2_credential,
    ssh_key,
    username_password,
)
from shared_core.connectors.decorators import (
    ConnectorClass,
    connector,
    get_provider_name,
    retryable,
    timed,
)
from shared_core.connectors.discovery import (
    DiscoveredPort,
    DiscoveryResult,
    discover_host,
    discover_ports,
)
from shared_core.connectors.exceptions import (
    AuthenticationFailedError,
    CapabilityNotSupportedError,
    CircuitBreakerOpenError,
    CommandExecutionError,
    ConnectionFailedError,
    ConnectorRateLimitExceededError,
    ConnectorTimeoutError,
    ConnectorValidationError,
    DiscoveryFailedError,
    FileTransferError,
    InventoryCollectionError,
    ProviderNotRegisteredError,
    SessionExpiredError,
)
from shared_core.connectors.factory import (
    build_connector_factory,
    create_connected_connector,
    create_connector,
)
from shared_core.connectors.health import (
    ConnectorHealthReport,
    build_health_report,
    connection_state_to_health,
)
from shared_core.connectors.helpers import connector_summary, format_bytes
from shared_core.connectors.inventory import InventoryReport
from shared_core.connectors.manager import ConnectorManager
from shared_core.connectors.metrics import (
    connector_bandwidth_bytes_total,
    connector_command_duration_seconds,
    connector_connections_total,
    connector_discovery_duration_seconds,
    connector_failure_total,
    connector_inventory_duration_seconds,
    connector_latency_seconds,
    connector_retries_total,
    connector_success_total,
    connector_transfer_size_bytes,
    measure_command,
    measure_discovery,
    measure_inventory,
    record_bandwidth,
    record_connection,
    record_failure,
    record_retry,
    record_success,
    record_transfer_size,
)
from shared_core.connectors.middleware import (
    Handler,
    Middleware,
    OperationContext,
    PermissionChecker,
    apply_middleware,
    audit_middleware,
    build_authentication_middleware,
    build_retry_middleware,
    build_security_middleware,
    build_telemetry_middleware,
    logging_middleware,
    metrics_collection_middleware,
    validation_middleware,
)
from shared_core.connectors.pool import ConnectorFactory, ConnectorPool
from shared_core.connectors.ratelimit import ConnectorRateLimiter, build_connector_rate_limiters
from shared_core.connectors.registry import ConnectorRegistry
from shared_core.connectors.retry import CircuitBreaker, CircuitState, connector_retry_policy
from shared_core.connectors.session import Session, new_session_id
from shared_core.connectors.telemetry import trace_operation
from shared_core.connectors.timeout import with_timeout
from shared_core.connectors.validation import (
    validate_capability,
    validate_certificate_expiry,
    validate_connection_config,
    validate_credential,
    validate_schema,
)

__all__ = [
    "AuthenticationFailedError",
    "AuthenticationResult",
    "Authenticator",
    "BaseConnector",
    "CapabilityNotSupportedError",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "CommandExecutionError",
    "CommandResult",
    "ConnectionConfig",
    "ConnectionFailedError",
    "ConnectionState",
    "ConnectorCapability",
    "ConnectorClass",
    "ConnectorFactory",
    "ConnectorHealthReport",
    "ConnectorManager",
    "ConnectorMetricsSnapshot",
    "ConnectorPool",
    "ConnectorRateLimitExceededError",
    "ConnectorRateLimiter",
    "ConnectorRegistry",
    "ConnectorTimeoutError",
    "ConnectorValidationError",
    "Credential",
    "CredentialType",
    "DiscoveredPort",
    "DiscoveryFailedError",
    "DiscoveryResult",
    "FileTransferError",
    "Handler",
    "InventoryCollectionError",
    "InventoryReport",
    "Middleware",
    "OperationContext",
    "PermissionChecker",
    "ProviderNotRegisteredError",
    "Session",
    "SessionExpiredError",
    "api_key",
    "apply_middleware",
    "audit_authenticate",
    "audit_command",
    "audit_connect",
    "audit_disconnect",
    "audit_discovery",
    "audit_failure",
    "audit_inventory",
    "audit_middleware",
    "audit_transfer",
    "authenticate",
    "bearer_token",
    "build_authentication_middleware",
    "build_connector_factory",
    "build_connector_rate_limiters",
    "build_health_report",
    "build_retry_middleware",
    "build_security_middleware",
    "build_telemetry_middleware",
    "certificate",
    "connection_state_to_health",
    "connector",
    "connector_bandwidth_bytes_total",
    "connector_command_duration_seconds",
    "connector_connections_total",
    "connector_discovery_duration_seconds",
    "connector_failure_total",
    "connector_inventory_duration_seconds",
    "connector_latency_seconds",
    "connector_retries_total",
    "connector_retry_policy",
    "connector_success_total",
    "connector_summary",
    "connector_transfer_size_bytes",
    "create_connected_connector",
    "create_connector",
    "discover_host",
    "discover_ports",
    "format_bytes",
    "get_provider_name",
    "jwt_credential",
    "logging_middleware",
    "measure_command",
    "measure_discovery",
    "measure_inventory",
    "metrics_collection_middleware",
    "new_session_id",
    "oauth2_credential",
    "record_bandwidth",
    "record_connection",
    "record_failure",
    "record_retry",
    "record_success",
    "record_transfer_size",
    "retryable",
    "ssh_key",
    "timed",
    "trace_operation",
    "username_password",
    "validate_capability",
    "validate_certificate_expiry",
    "validate_connection_config",
    "validate_credential",
    "validate_schema",
    "validation_middleware",
    "with_timeout",
]
