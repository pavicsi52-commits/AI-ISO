"""How each source's rows become graph nodes and relationships.

One mapper per source, each a pure function from rows to
``(nodes, relationships)``. Pure on purpose: mapping is where a sync
gets subtly wrong, and a pure function can be tested against a payload
without standing up ten services and a graph.

**Every mapper projects a narrow field set.** Synchronization reads with
a service token (see :mod:`app.clients.platform`), so a mapper that
copied whole source rows into the graph would launder privileged data
into a store with different access rules. What belongs here is
identity, type, and relationships -- the things a topology needs --
plus a small, named set of descriptive properties.

**A row that cannot be mapped is rejected, not guessed at.** A node with
no stable key cannot be merged, matched, or joined to its metadata, so
it is counted as a rejection with a reason rather than written under an
invented identifier.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.graph.entities import NodeInput, RelationshipInput
from app.models.enums import NodeType, RelationshipType, SyncSource

_KEY_FIELDS = ("key", "id", "uuid", "identifier", "asset_id", "resource_id")
"""Field names a source might use for its stable identifier, in preference order.

Not a guess so much as an accommodation: the platform's services were
written by different prompts and settled on different names for the
same idea.
"""

_NAME_FIELDS = ("name", "display_name", "title", "hostname", "label")


@dataclass(slots=True)
class MappedBatch:
    """What one mapper produced from one page of rows."""

    nodes: list[NodeInput] = field(default_factory=list)
    relationships: list[RelationshipInput] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)

    def extend(self, other: MappedBatch) -> None:
        """Fold another batch into this one."""
        self.nodes.extend(other.nodes)
        self.relationships.extend(other.relationships)
        self.rejections.extend(other.rejections)

    @property
    def is_empty(self) -> bool:
        """Whether anything at all was produced."""
        return not self.nodes and not self.relationships


def pick(row: dict[str, Any], names: Sequence[str]) -> str | None:
    """The first non-empty value among *names*, as a string."""
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def scoped_key(source: SyncSource, raw_key: str) -> str:
    """Namespace a source's identifier so two sources cannot collide.

    Inventory asset ``42`` and automation job ``42`` are different
    things. Without the prefix they would merge into one node, and the
    resulting graph would be confidently wrong in a way no error
    surfaces.
    """
    return f"{source}:{raw_key}"


def _reject(row: dict[str, Any], reason: str) -> dict[str, Any]:
    """Record why one row could not be mapped."""
    return {"reason": reason, "row": {k: row.get(k) for k in list(row)[:6]}}


def _node(
    source: SyncSource,
    row: dict[str, Any],
    *,
    node_type: NodeType,
    properties: dict[str, Any] | None = None,
) -> NodeInput | None:
    """Build a node from a row, or ``None`` if it has no usable identity."""
    raw_key = pick(row, _KEY_FIELDS)
    if not raw_key:
        return None
    return NodeInput(
        key=scoped_key(source, raw_key),
        node_type=node_type,
        name=pick(row, _NAME_FIELDS) or raw_key,
        description=_optional(row.get("description")),
        project_id=_optional(row.get("project_id")),
        source=str(source),
        properties=properties or {},
    )


def _optional(value: Any) -> str | None:
    """Coerce to ``str``, keeping empty and ``None`` as ``None``."""
    return None if value in (None, "") else str(value)


def _link(
    source: SyncSource,
    row: dict[str, Any],
    *,
    from_key: str,
    to_field: str,
    relationship_type: RelationshipType,
    weight: float = 1.0,
) -> RelationshipInput | None:
    """Build a relationship from a row's reference field, if it has one."""
    target = row.get(to_field)
    if target in (None, ""):
        return None
    to_key = scoped_key(source, str(target))
    if to_key == from_key:
        # A self-reference makes every dependency traversal cyclic; the
        # entity model refuses it, so it is dropped here rather than
        # raised on a whole batch.
        return None
    return RelationshipInput(
        from_key=from_key,
        to_key=to_key,
        relationship_type=relationship_type,
        weight=weight,
    )


_ASSET_TYPE_LABELS: dict[str, NodeType] = {
    "physical_server": NodeType.PHYSICAL_SERVER,
    "server": NodeType.PHYSICAL_SERVER,
    "virtual_machine": NodeType.VIRTUAL_MACHINE,
    "vm": NodeType.VIRTUAL_MACHINE,
    "hypervisor": NodeType.HYPERVISOR,
    "container": NodeType.CONTAINER,
    "kubernetes_cluster": NodeType.KUBERNETES_CLUSTER,
    "namespace": NodeType.NAMESPACE,
    "pod": NodeType.POD,
    "service": NodeType.SERVICE,
    "deployment": NodeType.DEPLOYMENT,
    "application": NodeType.APPLICATION,
    "database": NodeType.DATABASE,
    "storage": NodeType.STORAGE,
    "switch": NodeType.SWITCH,
    "router": NodeType.ROUTER,
    "firewall": NodeType.FIREWALL,
    "load_balancer": NodeType.LOAD_BALANCER,
    "network_interface": NodeType.NETWORK_INTERFACE,
    "cloud_account": NodeType.CLOUD_ACCOUNT,
    "cloud_resource": NodeType.CLOUD_RESOURCE,
    "edge_device": NodeType.EDGE_DEVICE,
    "industrial_controller": NodeType.INDUSTRIAL_CONTROLLER,
    "plc": NodeType.PLC,
    "sensor": NodeType.SENSOR,
    "opc_ua_server": NodeType.OPC_UA_SERVER,
    "site": NodeType.SITE,
    "region": NodeType.REGION,
    "data_center": NodeType.DATA_CENTER,
    "rack": NodeType.RACK,
}
"""Source asset-type strings to graph labels.

A dispatch table rather than a chain of branches, so an unmapped type
falls through to ``CUSTOM_NODE`` visibly instead of silently taking
another type's label. That fallback is deliberate: a new asset kind in
inventory should appear in the graph as an unclassified node, not
vanish from it.
"""


def classify_asset(row: dict[str, Any]) -> NodeType:
    """The graph label for one inventory or discovery row."""
    declared = str(row.get("asset_type") or row.get("type") or row.get("kind") or "").lower()
    return _ASSET_TYPE_LABELS.get(declared, NodeType.CUSTOM_NODE)


def map_inventory(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Assets, and where they run ("Synchronize: Inventory")."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.INVENTORY,
            row,
            node_type=classify_asset(row),
            properties={
                "environment": row.get("environment"),
                "status": row.get("status"),
                "location": row.get("location"),
            },
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        for field_name, edge_type in (
            ("parent_id", RelationshipType.PART_OF),
            ("host_id", RelationshipType.RUNS_ON),
            ("rack_id", RelationshipType.CONTAINS),
            ("site_id", RelationshipType.BELONGS_TO),
        ):
            edge = _link(
                SyncSource.INVENTORY,
                row,
                from_key=node.key,
                to_field=field_name,
                relationship_type=edge_type,
            )
            if edge is not None:
                batch.relationships.append(edge)
    return batch


def map_discovery(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Discovered assets and the links between them ("Synchronize: Discovery")."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.DISCOVERY,
            row,
            node_type=classify_asset(row),
            properties={
                "ip_address": row.get("ip_address"),
                "discovered_at": row.get("discovered_at"),
                "protocol": row.get("protocol"),
            },
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        for field_name, edge_type in (
            ("connected_to_id", RelationshipType.CONNECTED_TO),
            ("gateway_id", RelationshipType.CONNECTED_TO),
        ):
            edge = _link(
                SyncSource.DISCOVERY,
                row,
                from_key=node.key,
                to_field=field_name,
                relationship_type=edge_type,
            )
            if edge is not None:
                batch.relationships.append(edge)
    return batch


def map_configuration(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Configuration profiles and what they configure."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.CONFIGURATION,
            row,
            node_type=NodeType.CONFIGURATION_PROFILE,
            properties={"version": row.get("version"), "status": row.get("status")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        for target in row.get("target_asset_ids") or []:
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.INVENTORY, str(target)),
                    relationship_type=RelationshipType.CONFIGURES,
                )
            )
    return batch


def map_automation(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Automation jobs and what they execute against."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.AUTOMATION,
            row,
            node_type=NodeType.AUTOMATION_JOB,
            properties={"status": row.get("status"), "schedule": row.get("schedule")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        edge = _link(
            SyncSource.AUTOMATION,
            row,
            from_key=node.key,
            to_field="playbook_id",
            relationship_type=RelationshipType.USES,
        )
        if edge is not None:
            batch.relationships.append(edge)
        for target in row.get("target_asset_ids") or []:
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.INVENTORY, str(target)),
                    relationship_type=RelationshipType.EXECUTES,
                )
            )
    return batch


def map_workflow(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Workflows and the automations they drive."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.WORKFLOW,
            row,
            node_type=NodeType.WORKFLOW,
            properties={"status": row.get("status"), "version": row.get("version")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        for target in row.get("automation_job_ids") or []:
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.AUTOMATION, str(target)),
                    relationship_type=RelationshipType.EXECUTES,
                )
            )
    return batch


def map_validation(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Validation profiles and what they validate."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.VALIDATION,
            row,
            node_type=NodeType.VALIDATION_PROFILE,
            properties={"status": row.get("status"), "severity": row.get("severity")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        for target in row.get("target_asset_ids") or []:
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.INVENTORY, str(target)),
                    relationship_type=RelationshipType.VALIDATES,
                )
            )
    return batch


def map_monitoring(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Monitors and what they watch."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.MONITORING,
            row,
            node_type=NodeType.SERVICE,
            properties={"status": row.get("status"), "check_type": row.get("check_type")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        # Built directly rather than through _link, because the target
        # is an *inventory* asset: _link scopes the key to the source
        # being mapped, which would point this edge at a monitoring node
        # that does not exist.
        if row.get("asset_id"):
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.INVENTORY, str(row["asset_id"])),
                    relationship_type=RelationshipType.MONITORS,
                )
            )
    return batch


def map_alerting(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Alerts and what they fired against."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.ALERTING,
            row,
            node_type=NodeType.ALERT,
            properties={"severity": row.get("severity"), "status": row.get("status")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        if row.get("asset_id"):
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.INVENTORY, str(row["asset_id"])),
                    relationship_type=RelationshipType.MONITORS,
                )
            )
    return batch


def map_reporting(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Reports and what generated them."""
    batch = MappedBatch()
    for row in rows:
        node = _node(
            SyncSource.REPORTING,
            row,
            node_type=NodeType.REPORT,
            properties={"category": row.get("category"), "status": row.get("status")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
    return batch


def map_administration(rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Users, teams, and roles, and who belongs to what."""
    batch = MappedBatch()
    for row in rows:
        kind = str(row.get("principal_type") or row.get("type") or "user").lower()
        node_type = {
            "user": NodeType.USER,
            "team": NodeType.TEAM,
            "role": NodeType.ROLE,
        }.get(kind, NodeType.USER)
        node = _node(
            SyncSource.ADMINISTRATION,
            row,
            node_type=node_type,
            properties={"email": row.get("email"), "status": row.get("status")},
        )
        if node is None:
            batch.rejections.append(_reject(row, "no stable identifier"))
            continue
        batch.nodes.append(node)
        for target in row.get("team_ids") or []:
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.ADMINISTRATION, str(target)),
                    relationship_type=RelationshipType.BELONGS_TO,
                )
            )
        for target in row.get("owns_asset_ids") or []:
            batch.relationships.append(
                RelationshipInput(
                    from_key=node.key,
                    to_key=scoped_key(SyncSource.INVENTORY, str(target)),
                    relationship_type=RelationshipType.OWNS,
                )
            )
    return batch


Mapper = Callable[[Sequence[dict[str, Any]]], MappedBatch]

MAPPERS: dict[SyncSource, Mapper] = {
    SyncSource.INVENTORY: map_inventory,
    SyncSource.DISCOVERY: map_discovery,
    SyncSource.CONFIGURATION: map_configuration,
    SyncSource.AUTOMATION: map_automation,
    SyncSource.WORKFLOW: map_workflow,
    SyncSource.VALIDATION: map_validation,
    SyncSource.MONITORING: map_monitoring,
    SyncSource.ALERTING: map_alerting,
    SyncSource.REPORTING: map_reporting,
    SyncSource.ADMINISTRATION: map_administration,
}
"""Source to the function that maps its rows.

Every :class:`~app.models.enums.SyncSource` member has an entry, and a
test asserts that -- a source declared in the enum with no mapper would
be silently skipped by the engine, which is the quiet kind of gap.
"""

SOURCE_PATHS: dict[SyncSource, str] = {
    SyncSource.INVENTORY: "/inventory/assets",
    SyncSource.DISCOVERY: "/discovery/results",
    SyncSource.CONFIGURATION: "/configurations/profiles",
    SyncSource.AUTOMATION: "/automation/jobs",
    SyncSource.WORKFLOW: "/workflows",
    SyncSource.VALIDATION: "/validation/profiles",
    SyncSource.MONITORING: "/monitoring/checks",
    SyncSource.ALERTING: "/alerts",
    SyncSource.REPORTING: "/reports",
    SyncSource.ADMINISTRATION: "/administration/principals",
}
"""The endpoint each source is read from."""


def map_rows(source: SyncSource, rows: Sequence[dict[str, Any]]) -> MappedBatch:
    """Map one page from *source*.

    An unknown source yields an empty batch rather than raising: the
    engine iterates a configured list, and one unmapped source must not
    abort a whole sync run.
    """
    mapper = MAPPERS.get(source)
    if mapper is None:
        return MappedBatch()
    return mapper(rows)


__all__ = [
    "MAPPERS",
    "SOURCE_PATHS",
    "MappedBatch",
    "Mapper",
    "classify_asset",
    "map_administration",
    "map_alerting",
    "map_automation",
    "map_configuration",
    "map_discovery",
    "map_inventory",
    "map_monitoring",
    "map_reporting",
    "map_rows",
    "map_validation",
    "map_workflow",
    "pick",
    "scoped_key",
]
