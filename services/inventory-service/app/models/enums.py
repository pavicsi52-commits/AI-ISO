"""Enumerations for the inventory service's persisted domain.

Per docs/036 "SUPPORTED ASSET TYPES"/"ASSET STATUS"/etc.
"""

from __future__ import annotations

from enum import StrEnum


class AssetType(StrEnum):
    """Per docs/036 "SUPPORTED ASSET TYPES" (44 values, verbatim)."""

    PHYSICAL_SERVER = "physical_server"
    VIRTUAL_MACHINE = "virtual_machine"
    BARE_METAL = "bare_metal"
    HYPERVISOR = "hypervisor"
    CONTAINER = "container"
    CONTAINER_IMAGE = "container_image"
    KUBERNETES_CLUSTER = "kubernetes_cluster"
    NAMESPACE = "namespace"
    POD = "pod"
    DEPLOYMENT = "deployment"
    STATEFUL_SET = "stateful_set"
    DAEMON_SET = "daemon_set"
    SERVICE = "service"
    INGRESS = "ingress"
    PERSISTENT_VOLUME = "persistent_volume"
    STORAGE_SYSTEM = "storage_system"
    SAN = "san"
    NAS = "nas"
    OBJECT_STORAGE = "object_storage"
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    LOAD_BALANCER = "load_balancer"
    WIRELESS_CONTROLLER = "wireless_controller"
    INDUSTRIAL_CONTROLLER = "industrial_controller"
    PLC = "plc"
    RTU = "rtu"
    DCS_CONTROLLER = "dcs_controller"
    OPC_UA_SERVER = "opc_ua_server"
    OPC_UA_DEVICE = "opc_ua_device"
    IOT_DEVICE = "iot_device"
    CLOUD_ACCOUNT = "cloud_account"
    CLOUD_REGION = "cloud_region"
    CLOUD_RESOURCE = "cloud_resource"
    APPLICATION = "application"
    MICROSERVICE = "microservice"
    DATABASE = "database"
    MIDDLEWARE = "middleware"
    MESSAGE_BROKER = "message_broker"
    WEB_SERVER = "web_server"
    API_GATEWAY = "api_gateway"
    MONITORING_AGENT = "monitoring_agent"
    AUTOMATION_AGENT = "automation_agent"
    VALIDATION_AGENT = "validation_agent"
    CUSTOM_ASSET = "custom_asset"


class AssetStatus(StrEnum):
    """Per docs/036 "ASSET STATUS" (9 values, verbatim)."""

    DISCOVERED = "discovered"
    REGISTERED = "registered"
    MANAGED = "managed"
    UNMANAGED = "unmanaged"
    PROVISIONING = "provisioning"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"
    ARCHIVED = "archived"
    DELETED = "deleted"


class HealthStatus(StrEnum):
    """Per docs/036 "HEALTH STATUS" (6 values, verbatim)."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"
    UNREACHABLE = "unreachable"


class LifecycleState(StrEnum):
    """Per docs/036 "LIFECYCLE" (7 values, verbatim)."""

    PLANNED = "planned"
    PROVISIONING = "provisioning"
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"
    DISPOSED = "disposed"
    ARCHIVED = "archived"


class Criticality(StrEnum):
    """Asset business criticality -- docs/036's own "ASSET MODEL" names
    "Criticality" as a required field without enumerating values; this
    is the standard four-tier scale every other AI-IOS severity/priority
    enum in this codebase already uses.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RelationshipType(StrEnum):
    """Per docs/036 "RELATIONSHIP MODEL" (16 values, verbatim)."""

    RUNS_ON = "runs_on"
    HOSTED_BY = "hosted_by"
    CONNECTED_TO = "connected_to"
    DEPENDS_ON = "depends_on"
    CONSUMES = "consumes"
    PROVIDES = "provides"
    OWNS = "owns"
    MANAGED_BY = "managed_by"
    PROTECTED_BY = "protected_by"
    REPLICATED_TO = "replicated_to"
    BACKED_UP_BY = "backed_up_by"
    CONTAINS = "contains"
    PART_OF = "part_of"
    MEMBER_OF = "member_of"
    COMMUNICATES_WITH = "communicates_with"
    CUSTOM_RELATIONSHIP = "custom_relationship"


class GroupType(StrEnum):
    """Per docs/036 "GROUPS" (7 values, verbatim)."""

    STATIC = "static"
    DYNAMIC = "dynamic"
    RULE_BASED = "rule_based"
    LOCATION = "location"
    APPLICATION = "application"
    ENVIRONMENT = "environment"
    CUSTOM = "custom"


class OwnerType(StrEnum):
    """Per docs/036 "OWNERSHIP" -- the principal-bearing roles only;
    Organization/Project are already the inherited tenant-scope columns
    every AI-IOS entity carries, not a distinct ownership row here.
    """

    BUSINESS_OWNER = "business_owner"
    TECHNICAL_OWNER = "technical_owner"
    SUPPORT_TEAM = "support_team"
    VENDOR = "vendor"
    DEPARTMENT = "department"


class CustomFieldType(StrEnum):
    """Per docs/036 "CUSTOM ATTRIBUTES": "Typed Values" -- the value
    types a custom field definition may declare and validate against.
    """

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    JSON = "json"


class DiscoverySource(StrEnum):
    """Where a correlated external discovery record originated -- per
    docs/036 "INVENTORY SYNCHRONIZATION": "Discovery Updates". The
    discovery engine itself is explicitly out of scope ("DO NOT
    IMPLEMENT"); this only names the kind of external system a
    ``asset_discovery_links`` row can correlate against.
    """

    AGENT = "agent"
    CLOUD_API = "cloud_api"
    KUBERNETES_API = "kubernetes_api"
    NETWORK_SCAN = "network_scan"
    MANUAL = "manual"
    EXTERNAL_CMDB = "external_cmdb"


class AuditOutcome(StrEnum):
    """Whether an audited administrative action succeeded or failed."""

    SUCCESS = "success"
    FAILURE = "failure"


class ImportFormat(StrEnum):
    """Per docs/036 "IMPORT" (CSV/Excel/JSON/YAML/ZIP)."""

    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    YAML = "yaml"
    ZIP = "zip"


class ExportFormat(StrEnum):
    """Per docs/036 "EXPORT" (CSV/Excel/JSON/YAML/PDF/ZIP)."""

    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    YAML = "yaml"
    PDF = "pdf"
    ZIP = "zip"


__all__ = [
    "AssetStatus",
    "AssetType",
    "AuditOutcome",
    "Criticality",
    "CustomFieldType",
    "DiscoverySource",
    "ExportFormat",
    "GroupType",
    "HealthStatus",
    "ImportFormat",
    "LifecycleState",
    "OwnerType",
    "RelationshipType",
]
