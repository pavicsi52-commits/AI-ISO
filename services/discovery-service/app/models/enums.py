"""Enumerations for the discovery service's persisted domain.

Per docs/037 "DISCOVERY MODES"/"SUPPORTED PROTOCOLS"/etc.
"""

from __future__ import annotations

from enum import StrEnum


class DiscoveryMode(StrEnum):
    """Per docs/037 "DISCOVERY MODES" (8 values, verbatim)."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    CONTINUOUS = "continuous"
    INCREMENTAL = "incremental"
    FULL_SCAN = "full_scan"
    AGENTLESS = "agentless"
    AGENT_BASED = "agent_based"
    HYBRID = "hybrid"


class ProtocolType(StrEnum):
    """Per docs/037 "SUPPORTED PROTOCOLS" (25 values, verbatim, plus
    "Plugin-Based Protocols" -> ``PLUGIN``).
    """

    SSH = "ssh"
    WINRM = "winrm"
    SNMP = "snmp"
    REDFISH = "redfish"
    IPMI = "ipmi"
    HTTP = "http"
    HTTPS = "https"
    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    LDAP = "ldap"
    DNS = "dns"
    NTP = "ntp"
    SMB = "smb"
    SFTP = "sftp"
    FTP = "ftp"
    OPC_UA = "opc_ua"
    MODBUS = "modbus"
    BACNET = "bacnet"
    MQTT = "mqtt"
    AMQP = "amqp"
    JMX = "jmx"
    WMI = "wmi"
    ICMP = "icmp"
    TCP = "tcp"
    UDP = "udp"
    PLUGIN = "plugin"


class TargetType(StrEnum):
    """What kind of address a :class:`DiscoveryTarget` names."""

    HOST = "host"
    SUBNET = "subnet"
    CIDR = "cidr"
    CLOUD_ACCOUNT = "cloud_account"
    KUBERNETES_CLUSTER = "kubernetes_cluster"
    INDUSTRIAL_NETWORK = "industrial_network"
    CUSTOM = "custom"


class ProfileType(StrEnum):
    """Per docs/037 "DISCOVERY PROFILES" (8 values, verbatim)."""

    QUICK_SCAN = "quick_scan"
    DEEP_SCAN = "deep_scan"
    NETWORK_SCAN = "network_scan"
    CLOUD_SCAN = "cloud_scan"
    KUBERNETES_SCAN = "kubernetes_scan"
    INDUSTRIAL_SCAN = "industrial_scan"
    APPLICATION_SCAN = "application_scan"
    CUSTOM = "custom"


class DiscoveryResultStatus(StrEnum):
    """The outcome of one protocol probe against one target."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"


class AssetClassification(StrEnum):
    """Per docs/037 "ASSET CLASSIFICATION" (10 values, verbatim)."""

    INFRASTRUCTURE = "infrastructure"
    NETWORK = "network"
    COMPUTE = "compute"
    STORAGE = "storage"
    CLOUD = "cloud"
    INDUSTRIAL = "industrial"
    APPLICATION = "application"
    DATABASE = "database"
    SERVICE = "service"
    CUSTOM = "custom"


class DiscoveryRelationshipType(StrEnum):
    """Per docs/037 "RELATIONSHIP DISCOVERY" (9 values, verbatim)."""

    RUNS_ON = "runs_on"
    CONNECTED_TO = "connected_to"
    DEPENDS_ON = "depends_on"
    HOSTED_BY = "hosted_by"
    CONTAINS = "contains"
    COMMUNICATES_WITH = "communicates_with"
    MANAGED_BY = "managed_by"
    MEMBER_OF = "member_of"
    PART_OF = "part_of"


class ScheduleType(StrEnum):
    """Per docs/037 "SCHEDULING" (4 values, verbatim)."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    CRON = "cron"
    INTERVAL = "interval"


class FailureReason(StrEnum):
    """Why one target's discovery probe failed."""

    TIMEOUT = "timeout"
    AUTH_FAILED = "auth_failed"
    UNREACHABLE = "unreachable"
    PROTOCOL_ERROR = "protocol_error"
    CREDENTIAL_MISSING = "credential_missing"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


class RuleType(StrEnum):
    """Per docs/037 "DISCOVERY RULES" (9 values, verbatim)."""

    INCLUDE = "include"
    EXCLUDE = "exclude"
    FILTER = "filter"
    ASSET_MATCHING = "asset_matching"
    CLASSIFICATION = "classification"
    RELATIONSHIP = "relationship"
    TAG_ASSIGNMENT = "tag_assignment"
    OWNER_ASSIGNMENT = "owner_assignment"
    PROJECT_ASSIGNMENT = "project_assignment"


class ClassifiedBy(StrEnum):
    """How an asset's classification was determined."""

    RULE = "rule"
    HEURISTIC = "heuristic"
    MANUAL = "manual"


class FilterAppliesTo(StrEnum):
    """What a :class:`DiscoveryFilter` filters."""

    TARGET = "target"
    ASSET = "asset"
    RELATIONSHIP = "relationship"


class CredentialType(StrEnum):
    """The kind of credential a :class:`DiscoveryCredential` references
    (the secret material itself always lives in
    ``services/secrets-management-service``, never here).
    """

    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    API_KEY = "api_key"
    CERTIFICATE = "certificate"
    TOKEN = "token"


class SyncStatus(StrEnum):
    """Whether a :class:`DiscoveryAsset` has been reconciled into the
    Inventory Service yet.
    """

    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"
    FAILED = "failed"


class AuditOutcome(StrEnum):
    """Whether an audited administrative action succeeded or failed."""

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "AssetClassification",
    "AuditOutcome",
    "ClassifiedBy",
    "CredentialType",
    "DiscoveryMode",
    "DiscoveryRelationshipType",
    "DiscoveryResultStatus",
    "FailureReason",
    "FilterAppliesTo",
    "ProfileType",
    "ProtocolType",
    "RuleType",
    "ScheduleType",
    "SyncStatus",
    "TargetType",
]
