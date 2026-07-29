"""Digital twins ("DIGITAL TWIN").

A twin is a *view* over a node and the subgraph beneath it, not a second
copy of that node. That is the whole design decision: the graph already
holds identity and relationships, and duplicating them into a separate
twin store would create two things that must agree and eventually will
not.

What a twin adds is the part the graph does not carry -- lifecycle
state, declared criticality, ownership, and health -- which lives in
:class:`~app.models.graph_metadata.GraphMetadata` in PostgreSQL and is
joined on the node key at read time.

**Health is composed, not stored.** A twin's health is the worst health
among itself and its components, because a host reporting "healthy"
while the database on it is down is not a useful statement about the
host. Recomputing on read means the answer cannot go stale; the cost is
one traversal, which is what a twin read is anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.health_status import HealthStatus

from app.graph.entities import GraphNode
from app.graph.repository import GraphRepository
from app.models.enums import (
    CONTAINMENT_TYPES,
    DEPENDENCY_TYPES,
    LifecycleState,
    NodeType,
    TraversalDirection,
    TwinType,
)
from app.models.graph_metadata import GraphMetadata
from app.repositories.graph_metadata import GraphMetadataRepository

_TWIN_NODE_TYPES: dict[TwinType, frozenset[NodeType]] = {
    TwinType.INFRASTRUCTURE: frozenset(
        {
            NodeType.PHYSICAL_SERVER,
            NodeType.VIRTUAL_MACHINE,
            NodeType.HYPERVISOR,
            NodeType.RACK,
            NodeType.DATA_CENTER,
            NodeType.SITE,
            NodeType.STORAGE,
            NodeType.SWITCH,
            NodeType.ROUTER,
            NodeType.FIREWALL,
            NodeType.LOAD_BALANCER,
            NodeType.NETWORK_INTERFACE,
        }
    ),
    TwinType.APPLICATION: frozenset(
        {
            NodeType.APPLICATION,
            NodeType.DEPLOYMENT,
            NodeType.POD,
            NodeType.CONTAINER,
            NodeType.DATABASE,
        }
    ),
    TwinType.CLOUD: frozenset({NodeType.CLOUD_ACCOUNT, NodeType.CLOUD_RESOURCE}),
    TwinType.INDUSTRIAL: frozenset(
        {
            NodeType.EDGE_DEVICE,
            NodeType.INDUSTRIAL_CONTROLLER,
            NodeType.PLC,
            NodeType.SENSOR,
            NodeType.OPC_UA_SERVER,
        }
    ),
    TwinType.SERVICE: frozenset(
        {NodeType.SERVICE, NodeType.KUBERNETES_CLUSTER, NodeType.NAMESPACE}
    ),
    TwinType.CONFIGURATION: frozenset(
        {NodeType.CONFIGURATION_PROFILE, NodeType.VALIDATION_PROFILE}
    ),
}
"""Which node types belong to each twin kind.

A table rather than a chain of branches: a node type added to the enum
and forgotten here falls through to "no twin type", which a test
asserts against -- an unclassified node type would otherwise be invisible
to every twin listing.
"""

_HEALTH_ORDER: dict[str, int] = {
    str(HealthStatus.HEALTHY): 0,
    str(HealthStatus.WARNING): 1,
    str(HealthStatus.DEGRADED): 2,
    str(HealthStatus.MAINTENANCE): 3,
    str(HealthStatus.UNHEALTHY): 4,
    str(HealthStatus.UNKNOWN): 5,
}
"""Health from best to worst.

**Every** :class:`~shared_core.enums.health_status.HealthStatus` member
has a rank -- all six, not the four of the original Prompt 012 baseline.
A missing member would fall through to ``UNKNOWN``'s rank, which would
make a merely ``WARNING`` component compose as the worst thing in the
twin. A test asserts the table stays complete as the enum grows.

``UNKNOWN`` sorts *worst*, not neutral. A component nobody is measuring
is not evidence of health, and treating it as such is how a twin reports
green while a third of it is unmonitored.

``MAINTENANCE`` sorts above ``DEGRADED`` and below ``UNHEALTHY``: it is
genuinely not serving, so it is worse than degraded, but it is planned,
so it is less alarming than an unplanned failure.
"""

_DEGRADED_LIFECYCLE = frozenset({LifecycleState.DEGRADED, LifecycleState.RETIRING})

_NON_OPERATIONAL_HEALTH = frozenset({HealthStatus.UNHEALTHY, HealthStatus.MAINTENANCE})
"""Health states in which a twin is not serving.

``MAINTENANCE`` belongs here even though it is planned -- "deliberately
out" and "unexpectedly out" are both out, and a caller asking
``is_operational`` is asking whether it can route traffic there.
"""


def twin_type_for(node_type: NodeType | str) -> TwinType | None:
    """Which twin kind a node type belongs to, or ``None``.

    ``None`` is a real answer: an alert or a report is a graph node but
    not a thing that has a digital twin.
    """
    resolved = node_type if isinstance(node_type, NodeType) else _as_node_type(node_type)
    if resolved is None:
        return None
    for twin_type, members in _TWIN_NODE_TYPES.items():
        if resolved in members:
            return twin_type
    return None


def _as_node_type(value: str) -> NodeType | None:
    """Coerce a stored label back to its enum member, or ``None``."""
    try:
        return NodeType(value)
    except ValueError:
        return None


def lifecycle_of(metadata: GraphMetadata) -> LifecycleState:
    """A metadata row's lifecycle state as a genuine enum member.

    ``lifecycle_state`` is annotated ``Mapped[LifecycleState]`` but
    stored in a ``String``, so a row loaded from Postgres yields a plain
    ``str``.
    """
    value = metadata.lifecycle_state
    return value if isinstance(value, LifecycleState) else LifecycleState(value)


def twin_type_of(metadata: GraphMetadata) -> TwinType | None:
    """A metadata row's twin type as a genuine enum member, or ``None``."""
    value = metadata.twin_type
    if value is None:
        return None
    return value if isinstance(value, TwinType) else TwinType(value)


def worst_health(values: list[str | None]) -> HealthStatus:
    """The worst health among *values*.

    An empty list is ``UNKNOWN`` rather than ``HEALTHY``: nothing
    measured is not the same as nothing wrong.
    """
    ranked = [
        _HEALTH_ORDER.get(str(one), _HEALTH_ORDER[str(HealthStatus.UNKNOWN)])
        for one in values
        if one is not None
    ]
    if not ranked:
        return HealthStatus.UNKNOWN
    worst = max(ranked)
    for name, rank in _HEALTH_ORDER.items():
        if rank == worst:
            return HealthStatus(name)
    return HealthStatus.UNKNOWN


@dataclass(slots=True)
class DigitalTwin:
    """One node, its components, and the state around it."""

    node: GraphNode
    twin_type: TwinType | None
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE
    health: HealthStatus = HealthStatus.UNKNOWN
    criticality: float = 0.0
    owner_team: str | None = None
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    components: list[GraphNode] = field(default_factory=list)
    dependencies: list[GraphNode] = field(default_factory=list)
    dependents: list[GraphNode] = field(default_factory=list)
    component_health: dict[str, str] = field(default_factory=dict)
    synchronised_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def component_count(self) -> int:
        """How many components the twin contains."""
        return len(self.components)

    @property
    def is_operational(self) -> bool:
        """Whether the twin is in a state that serves traffic.

        Lifecycle and health both have to hold: a retired node reporting
        healthy is not operational, and neither is an active one that is
        down or in maintenance.
        """
        return (
            self.lifecycle_state is LifecycleState.ACTIVE
            and self.health not in _NON_OPERATIONAL_HEALTH
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "node": self.node.as_dict(),
            "twin_type": str(self.twin_type) if self.twin_type else None,
            "lifecycle_state": str(self.lifecycle_state),
            "health": str(self.health),
            "is_operational": self.is_operational,
            "criticality": self.criticality,
            "owner_team": self.owner_team,
            "tags": self.tags,
            "attributes": self.attributes,
            "components": [one.as_dict() for one in self.components],
            "component_count": self.component_count,
            "dependencies": [one.as_dict() for one in self.dependencies],
            "dependents": [one.as_dict() for one in self.dependents],
            "component_health": self.component_health,
            "synchronised_at": self.synchronised_at.isoformat(),
        }


class DigitalTwinService:
    """Builds and maintains digital twins."""

    def __init__(
        self,
        graph: GraphRepository,
        metadata: GraphMetadataRepository,
        *,
        component_depth: int = 2,
    ) -> None:
        self._graph = graph
        self._metadata = metadata
        self._component_depth = component_depth

    async def build(self, organization_id: UUID, node_key: str) -> DigitalTwin:
        """Assemble the twin for one node.

        Raises:
            NotFoundError: If the node does not exist.
            DependencyError: If the graph is unreachable.
        """
        node = await self._graph.require_node(organization_id, node_key)
        twin = DigitalTwin(node=node, twin_type=twin_type_for(node.node_type))

        stored = await self._metadata.get_for_node(organization_id, node_key)
        if stored is not None:
            twin.lifecycle_state = lifecycle_of(stored)
            twin.criticality = stored.criticality
            twin.owner_team = stored.owner_team
            twin.tags = list(stored.tags or [])
            twin.attributes = dict(stored.attributes or {})

        contained = await self._graph.traverse(
            organization_id,
            node_key,
            direction=TraversalDirection.INCOMING,
            relationship_types=sorted(CONTAINMENT_TYPES),
            depth=self._component_depth,
        )
        twin.components = [one for one in contained.nodes if one.key != node_key]

        downstream = await self._graph.neighbours(
            organization_id,
            node_key,
            direction=TraversalDirection.OUTGOING,
            relationship_types=sorted(DEPENDENCY_TYPES),
        )
        twin.dependencies = [one for one in downstream if one.key != node_key]

        upstream = await self._graph.neighbours(
            organization_id,
            node_key,
            direction=TraversalDirection.INCOMING,
            relationship_types=sorted(DEPENDENCY_TYPES),
        )
        twin.dependents = [one for one in upstream if one.key != node_key]

        await self._apply_health(organization_id, twin, stored)
        return twin

    async def _apply_health(
        self,
        organization_id: UUID,
        twin: DigitalTwin,
        stored: GraphMetadata | None,
    ) -> None:
        """Compose the twin's health from its own and its components'.

        One batched metadata read for every component rather than one
        per component: a twin with two hundred components would
        otherwise be two hundred round trips to answer one question.
        """
        component_keys = [one.key for one in twin.components]
        component_metadata = await self._metadata.get_many(organization_id, component_keys)
        twin.component_health = {
            key: str(row.health_status)
            for key, row in component_metadata.items()
            if row.health_status
        }

        own = stored.health_status if stored is not None else None
        if stored is not None and lifecycle_of(stored) in _DEGRADED_LIFECYCLE:
            # A node its operator has marked degraded or retiring is not
            # healthy however its checks read.
            own = str(HealthStatus.DEGRADED)
        twin.health = worst_health([own, *twin.component_health.values()])

    async def set_state(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        lifecycle_state: LifecycleState | None = None,
        health_status: HealthStatus | None = None,
        criticality: float | None = None,
        owner_team: str | None = None,
        tags: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        is_pinned: bool | None = None,
        actor_id: UUID | None = None,
    ) -> GraphMetadata:
        """Record twin state, creating the metadata row if needed.

        Raises:
            NotFoundError: If the node does not exist. Metadata for a
                node that is not in the graph would be unreachable by
                every read path that joins on the node key.
        """
        node = await self._graph.require_node(organization_id, node_key)
        stored = await self._metadata.get_for_node(organization_id, node_key)
        created = stored is None
        if stored is None:
            stored = GraphMetadata(
                organization_id=organization_id,
                node_key=node_key,
                node_type=node.node_type,
                display_name=node.name,
                twin_type=twin_type_for(node.node_type),
            )

        if lifecycle_state is not None:
            stored.lifecycle_state = lifecycle_state
        if health_status is not None:
            stored.health_status = str(health_status)
        if criticality is not None:
            stored.criticality = max(0.0, min(1.0, criticality))
        if owner_team is not None:
            stored.owner_team = owner_team
        if tags is not None:
            stored.tags = tags
        if attributes is not None:
            stored.attributes = attributes
        if is_pinned is not None:
            stored.is_pinned = is_pinned
        if actor_id is not None:
            stored.updated_by = actor_id

        if created:
            return await self._metadata.create(stored)
        return await self._metadata.update(stored)

    async def list_twins(
        self,
        organization_id: UUID,
        *,
        twin_type: TwinType | None = None,
        lifecycle_state: LifecycleState | None = None,
        limit: int = 200,
    ) -> list[GraphMetadata]:
        """Metadata rows for the twins an organization tracks."""
        return await self._metadata.list_for_org(
            organization_id,
            twin_type=twin_type,
            lifecycle_state=lifecycle_state,
            limit=limit,
        )

    async def twin_counts(self, organization_id: UUID) -> dict[str, int]:
        """How many twins of each kind an organization tracks."""
        rows = await self._metadata.list_for_org(organization_id, limit=10_000)
        counts: dict[str, int] = {}
        for row in rows:
            kind = twin_type_of(row)
            if kind is None:
                continue
            counts[str(kind)] = counts.get(str(kind), 0) + 1
        return counts


__all__ = [
    "DigitalTwin",
    "DigitalTwinService",
    "lifecycle_of",
    "twin_type_for",
    "twin_type_of",
    "worst_health",
]
