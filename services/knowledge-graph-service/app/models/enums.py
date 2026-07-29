"""Enumerations for the Knowledge Graph Service, per docs/049.

**Reuse note**: ``shared_core.enums`` already owns the platform-wide
vocabularies this service consumes rather than redefines --
``Severity`` for risk bands, ``NotificationChannel``/``NotificationType``
for delivery, ``HealthStatus`` for twin health.

Every enum is a :class:`~enum.StrEnum` so it round-trips through the
``String`` columns this platform uses. **That also means a value loaded
back from Postgres is a plain ``str``, not an enum member** -- compare
with ``==``, or normalise first; never ``is``. That mistake has now
shipped as a live bug four times across this platform (prompt
templates, alert maintenance windows, automation dispatch, and GitOps
conflict detection), so every comparison in this service goes through
an explicit normaliser.

**Node and relationship types are also the Neo4j label vocabulary**, and
that is what makes them security-relevant. A Cypher label cannot be
supplied as a bound parameter -- it is part of the query text -- so the
*only* labels this service will ever write into a query are the members
below, checked by :func:`app.cypher.builder.validate_label`. Anything
else is refused. ``CUSTOM_NODE`` and ``CUSTOM_RELATIONSHIP`` exist so an
installation with its own vocabulary has a supported home for it
without needing a label this service cannot vet.
"""

from __future__ import annotations

from enum import StrEnum


class NodeType(StrEnum):
    """Per docs/049 "GRAPH NODE TYPES".

    The value is the Neo4j label, so these are PascalCase rather than
    the snake_case this platform uses elsewhere: ``MATCH (n:VirtualMachine)``
    is the idiomatic form every Neo4j tool and operator expects.
    """

    ORGANIZATION = "Organization"
    PROJECT = "Project"
    SITE = "Site"
    REGION = "Region"
    DATA_CENTER = "DataCenter"
    RACK = "Rack"
    PHYSICAL_SERVER = "PhysicalServer"
    VIRTUAL_MACHINE = "VirtualMachine"
    HYPERVISOR = "Hypervisor"
    CONTAINER = "Container"
    KUBERNETES_CLUSTER = "KubernetesCluster"
    NAMESPACE = "Namespace"
    POD = "Pod"
    SERVICE = "Service"
    DEPLOYMENT = "Deployment"
    APPLICATION = "Application"
    DATABASE = "Database"
    STORAGE = "Storage"
    SWITCH = "Switch"
    ROUTER = "Router"
    FIREWALL = "Firewall"
    LOAD_BALANCER = "LoadBalancer"
    NETWORK_INTERFACE = "NetworkInterface"
    CLOUD_ACCOUNT = "CloudAccount"
    CLOUD_RESOURCE = "CloudResource"
    EDGE_DEVICE = "EdgeDevice"
    INDUSTRIAL_CONTROLLER = "IndustrialController"
    PLC = "PLC"
    SENSOR = "Sensor"
    OPC_UA_SERVER = "OpcUaServer"
    WORKFLOW = "Workflow"
    AUTOMATION_JOB = "AutomationJob"
    PLAYBOOK = "Playbook"
    VALIDATION_PROFILE = "ValidationProfile"
    CONFIGURATION_PROFILE = "ConfigurationProfile"
    ALERT = "Alert"
    INCIDENT = "Incident"
    REPORT = "Report"
    USER = "User"
    TEAM = "Team"
    ROLE = "Role"
    CUSTOM_NODE = "CustomNode"


class RelationshipType(StrEnum):
    """Per docs/049 "RELATIONSHIP TYPES".

    SCREAMING_SNAKE_CASE because that is the Neo4j convention for
    relationship types, and these values *are* the types.
    """

    HOSTS = "HOSTS"
    RUNS_ON = "RUNS_ON"
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"
    CONNECTED_TO = "CONNECTED_TO"
    COMMUNICATES_WITH = "COMMUNICATES_WITH"
    OWNS = "OWNS"
    BELONGS_TO = "BELONGS_TO"
    PART_OF = "PART_OF"
    PROTECTS = "PROTECTS"
    MONITORS = "MONITORS"
    VALIDATES = "VALIDATES"
    CONFIGURES = "CONFIGURES"
    EXECUTES = "EXECUTES"
    GENERATES = "GENERATES"
    USES = "USES"
    MANAGES = "MANAGES"
    REPLICATES_TO = "REPLICATES_TO"
    BACKS_UP = "BACKS_UP"
    CUSTOM_RELATIONSHIP = "CUSTOM_RELATIONSHIP"


DEPENDENCY_TYPES: frozenset[RelationshipType] = frozenset(
    {
        RelationshipType.DEPENDS_ON,
        RelationshipType.RUNS_ON,
        RelationshipType.USES,
        RelationshipType.CONNECTED_TO,
        RelationshipType.COMMUNICATES_WITH,
    }
)
"""Relationships that carry an operational dependency.

Used as the default edge set for dependency, impact, and blast-radius
analysis. ``OWNS`` and ``BELONGS_TO`` are deliberately excluded: a team
owning a server is an organisational fact, not a failure path, and
including it would make every blast radius sweep in the whole
organisation chart.
"""

CONTAINMENT_TYPES: frozenset[RelationshipType] = frozenset(
    {
        RelationshipType.CONTAINS,
        RelationshipType.HOSTS,
        RelationshipType.PART_OF,
    }
)
"""Relationships that express physical or logical containment."""


class TwinType(StrEnum):
    """Per docs/049 "DIGITAL TWIN"."""

    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"
    CLOUD = "cloud"
    INDUSTRIAL = "industrial"
    SERVICE = "service"
    CONFIGURATION = "configuration"


class LifecycleState(StrEnum):
    """Where a twin is in its life ("Lifecycle Tracking")."""

    PLANNED = "planned"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    RETIRING = "retiring"
    RETIRED = "retired"


class SyncSource(StrEnum):
    """Per docs/049 "GRAPH SYNCHRONIZATION"."""

    INVENTORY = "inventory"
    DISCOVERY = "discovery"
    CONFIGURATION = "configuration"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    REPORTING = "reporting"
    ADMINISTRATION = "administration"


class SyncMode(StrEnum):
    """How much of a source one run pulls."""

    FULL = "full"
    INCREMENTAL = "incremental"


class SyncStatus(StrEnum):
    """Where one synchronization run stands."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    DISABLED = "disabled"


class ConflictResolution(StrEnum):
    """What happens when a sync and the graph disagree ("Conflict Resolution")."""

    SOURCE_WINS = "source_wins"
    GRAPH_WINS = "graph_wins"
    NEWEST_WINS = "newest_wins"
    MANUAL = "manual"


class QueryKind(StrEnum):
    """Per docs/049 "GRAPH QUERIES"."""

    DEPENDENCY_LOOKUP = "dependency_lookup"
    IMPACT_ANALYSIS = "impact_analysis"
    BLAST_RADIUS = "blast_radius"
    SHORTEST_PATH = "shortest_path"
    RELATIONSHIP_TRAVERSAL = "relationship_traversal"
    NEIGHBOR_DISCOVERY = "neighbor_discovery"
    TOPOLOGY = "topology"
    OWNERSHIP = "ownership"
    SERVICE_DEPENDENCY = "service_dependency"
    CONFIGURATION_DEPENDENCY = "configuration_dependency"
    AUTOMATION_DEPENDENCY = "automation_dependency"
    WORKFLOW_DEPENDENCY = "workflow_dependency"
    CUSTOM_CYPHER = "custom_cypher"


class TraversalDirection(StrEnum):
    """Which way a traversal follows its edges.

    The distinction is the whole point of dependency analysis:
    ``OUTGOING`` answers "what do I need?" and ``INCOMING`` answers "who
    breaks if I go down?". Getting it backwards produces a confident,
    wrong answer to the question an operator most needs during an
    incident.
    """

    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class AnalyticsAlgorithm(StrEnum):
    """Per docs/049 "GRAPH ANALYTICS"."""

    DEGREE_CENTRALITY = "degree_centrality"
    BETWEENNESS_CENTRALITY = "betweenness_centrality"
    PAGERANK = "pagerank"
    COMMUNITY_DETECTION = "community_detection"
    CONNECTED_COMPONENTS = "connected_components"
    SHORTEST_PATH = "shortest_path"
    CRITICAL_ASSETS = "critical_assets"
    RISK_PROPAGATION = "risk_propagation"
    DEPENDENCY_SCORING = "dependency_scoring"
    RELATIONSHIP_DENSITY = "relationship_density"


class GraphFormat(StrEnum):
    """Per docs/049 "IMPORT / EXPORT"."""

    CYPHER = "cypher"
    GRAPHML = "graphml"
    CSV = "csv"
    JSON = "json"


class JobStatus(StrEnum):
    """Where an import, export, or snapshot job stands."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChangeAction(StrEnum):
    """What one recorded graph change did ("Change Tracking")."""

    NODE_CREATED = "node.created"
    NODE_UPDATED = "node.updated"
    NODE_DELETED = "node.deleted"
    RELATIONSHIP_CREATED = "relationship.created"
    RELATIONSHIP_UPDATED = "relationship.updated"
    RELATIONSHIP_DELETED = "relationship.deleted"


class AuditAction(StrEnum):
    """Per docs/049 "AUDIT"."""

    NODE_CHANGED = "node.changed"
    RELATIONSHIP_CHANGED = "relationship.changed"
    SYNCHRONIZED = "graph.synchronized"
    IMPORTED = "graph.imported"
    EXPORTED = "graph.exported"
    QUERIED = "graph.queried"
    CYPHER_EXECUTED = "graph.cypher_executed"
    SNAPSHOT_TAKEN = "graph.snapshot_taken"
    VERSION_CREATED = "graph.version_created"
    ADMINISTRATIVE = "graph.administrative"


class AuditOutcome(StrEnum):
    """Whether an audited action succeeded."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


__all__ = [
    "CONTAINMENT_TYPES",
    "DEPENDENCY_TYPES",
    "AnalyticsAlgorithm",
    "AuditAction",
    "AuditOutcome",
    "ChangeAction",
    "ConflictResolution",
    "GraphFormat",
    "JobStatus",
    "LifecycleState",
    "NodeType",
    "QueryKind",
    "RelationshipType",
    "SyncMode",
    "SyncSource",
    "SyncStatus",
    "TraversalDirection",
    "TwinType",
]
