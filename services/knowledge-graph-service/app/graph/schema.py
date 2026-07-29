"""The Neo4j schema: constraints and indexes.

Per docs/049 "OUTPUT": generate the Neo4j schema. Neo4j is schema-
optional, which means the schema is whatever the writes happen to
produce unless something states it -- this module is that statement, and
it is applied at startup.

**The uniqueness constraint is the important one.** Every node carries a
``key``, the stable business identifier the source service owns, and
``(key, organization_id)`` is unique. That single constraint is what
makes synchronization idempotent: ``MERGE`` on it either finds the
existing node or creates one, so re-running a full sync updates the
graph instead of doubling it. Without the constraint ``MERGE`` still
works but has no index behind it, and a sync over a large estate turns
into a full scan per node.

**Every index is composite on ``organization_id`` first.** Every query
this service builds is tenant-scoped, so an index that does not lead
with the tenant is an index most queries cannot use.

Applying is idempotent -- ``IF NOT EXISTS`` throughout -- so startup can
run it unconditionally rather than tracking whether it has.
"""

from __future__ import annotations

from shared_core.logging.logger import get_logger

from app.graph.client import GraphClient
from app.models.enums import NodeType

logger = get_logger("app.graph.schema")

NODE_KEY_CONSTRAINT = "graph_node_key_unique"
"""Name of the constraint that makes synchronization idempotent."""

_CONSTRAINTS: tuple[str, ...] = (
    # The one that matters: identity. MERGE on (key, organization_id)
    # is how a re-run updates rather than duplicates. Uniqueness
    # constraints are available on Community as well as Enterprise.
    f"CREATE CONSTRAINT {NODE_KEY_CONSTRAINT} IF NOT EXISTS "
    "FOR (n:GraphNode) REQUIRE (n.key, n.organization_id) IS UNIQUE",
)

_ENTERPRISE_CONSTRAINTS: tuple[str, ...] = (
    # A node with no key cannot be merged, matched, or joined to its
    # metadata row -- it is unreachable data.
    "CREATE CONSTRAINT graph_node_key_exists IF NOT EXISTS "
    "FOR (n:GraphNode) REQUIRE n.key IS NOT NULL",
    # A node with no organization is visible to every tenant scope or
    # to none. Both are wrong, and the second is the quiet one.
    "CREATE CONSTRAINT graph_node_org_exists IF NOT EXISTS "
    "FOR (n:GraphNode) REQUIRE n.organization_id IS NOT NULL",
)
"""Property-existence constraints, which **Neo4j Community rejects**.

Verified against Neo4j Kernel 5.26.28 Community: "Property existence
constraint requires Neo4j Enterprise Edition." They are attempted
anyway, because on Enterprise they are worth having and skipping them
there would be a silent downgrade.

On Community the invariants still hold -- they are enforced one layer
up instead, which is where they have to hold regardless:
:class:`~app.graph.entities.NodeInput` requires a non-empty ``key``,
and every write in :mod:`app.graph.repository` binds
``organization_id`` as a parameter of the ``MERGE`` pattern itself, so
a node cannot be written without one. The constraint is defence in
depth, not the only defence.

Their absence is reported at INFO rather than WARNING so it does not
look like a fault on every Community startup.
"""

_ENTERPRISE_ONLY_MARKER = "enterprise edition"

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX graph_node_org_type IF NOT EXISTS "
    "FOR (n:GraphNode) ON (n.organization_id, n.node_type)",
    "CREATE INDEX graph_node_org_name IF NOT EXISTS "
    "FOR (n:GraphNode) ON (n.organization_id, n.name)",
    "CREATE INDEX graph_node_project IF NOT EXISTS "
    "FOR (n:GraphNode) ON (n.organization_id, n.project_id)",
    "CREATE INDEX graph_node_source IF NOT EXISTS "
    "FOR (n:GraphNode) ON (n.organization_id, n.source)",
    "CREATE INDEX graph_node_updated IF NOT EXISTS "
    "FOR (n:GraphNode) ON (n.organization_id, n.updated_at)",
)

_FULLTEXT_INDEX = (
    "CREATE FULLTEXT INDEX graph_node_search IF NOT EXISTS "
    "FOR (n:GraphNode) ON EACH [n.name, n.description, n.key]"
)
"""Full-text index behind ``GET /graph/search`` ("SEARCH").

Separate from the composite indexes because a full-text index cannot
lead with ``organization_id`` -- Neo4j full-text indexes are over the
listed properties only. The tenant filter is therefore applied to the
*results*, in the same query, rather than by the index. That is the one
place tenant scoping is a predicate rather than an index prefix, and it
is why the search query always carries its ``organization_id``
parameter.
"""

GRAPH_NODE_LABEL = "GraphNode"
"""The label every node carries in addition to its own type.

Two labels per node -- ``:GraphNode:VirtualMachine`` -- so that one
constraint and one index set covers everything, while a query that
wants only virtual machines still gets a label-scoped scan. Declaring
the constraint on all forty node types instead would mean forty
constraints and forty indexes to keep in step.
"""


def node_labels(node_type: NodeType | str) -> str:
    """Render the label list a node is written with.

    Always the shared label plus the specific one, in that order.
    """
    return f"{GRAPH_NODE_LABEL}:{node_type}"


async def apply_schema(client: GraphClient) -> int:
    """Create every constraint and index; returns how many statements ran.

    Idempotent, and **never fatal**. A deployment where the graph is
    briefly unavailable at startup should come up and report itself
    not-ready, not crash-loop -- so a failure here is logged and the
    service continues. Everything is re-applied on the next start.
    """
    if not client.enabled:
        logger.info("Graph schema not applied: Neo4j is not configured.")
        return 0

    applied = 0
    for statement in (*_CONSTRAINTS, *_INDEXES, _FULLTEXT_INDEX):
        if await _try_apply(client, statement, enterprise_only=False):
            applied += 1

    # Asked, not attempted-and-caught: issuing a statement we know will
    # be refused logs a failed write on every Community startup, and a
    # log line that always appears is a log line nobody reads.
    enterprise = 0
    if await is_enterprise(client):
        for statement in _ENTERPRISE_CONSTRAINTS:
            if await _try_apply(client, statement, enterprise_only=True):
                enterprise += 1
    else:
        logger.info(
            "Property-existence constraints skipped: this Neo4j is Community "
            "Edition, which does not support them. The same invariants are "
            "enforced a layer up -- app.graph.entities requires a non-empty key, "
            "and every write in app.graph.repository binds organization_id into "
            "the MERGE pattern itself.",
            extra={"extra_fields": {"skipped": len(_ENTERPRISE_CONSTRAINTS)}},
        )

    total = applied + enterprise
    logger.info(
        "Graph schema applied.",
        extra={"extra_fields": {"statements": total, "database": client.database}},
    )
    return total


async def is_enterprise(client: GraphClient) -> bool:
    """Whether this Neo4j is Enterprise Edition.

    Unreadable edition counts as Community: attempting an
    Enterprise-only statement and failing is noisier than skipping one
    that might have worked.
    """
    if not client.enabled:
        return False
    try:
        result = await client.read("CALL dbms.components() YIELD edition RETURN edition LIMIT 1")
    except Exception:
        return False
    return str(result.scalar("edition", "")).lower() == "enterprise"


async def _try_apply(client: GraphClient, statement: str, *, enterprise_only: bool) -> bool:
    """Run one schema statement; returns whether it applied.

    An Enterprise-only refusal is tolerated quietly -- the edition probe
    should have prevented reaching here, but a mixed cluster could still
    produce one. Anything else is a real problem and gets a warning
    naming the statement.
    """
    try:
        await client.write(statement)
    except Exception as exc:
        if enterprise_only and _ENTERPRISE_ONLY_MARKER in str(exc).lower():
            return False
        logger.warning(
            "Could not apply a graph schema statement; the service will start anyway.",
            extra={"extra_fields": {"statement": statement[:80], "error": str(exc)}},
        )
        return False
    return True


async def describe_schema(client: GraphClient) -> dict[str, list[str]]:
    """Report the constraints and indexes the database actually has.

    Reads from Neo4j rather than echoing the constants above, so the
    answer is what *is* rather than what should be -- the difference
    being exactly what an operator is looking for when a query is slow.
    """
    if not client.enabled:
        return {"constraints": [], "indexes": []}
    constraints = await client.read("SHOW CONSTRAINTS YIELD name RETURN name")
    indexes = await client.read("SHOW INDEXES YIELD name RETURN name")
    return {
        "constraints": sorted(str(row.get("name")) for row in constraints.records),
        "indexes": sorted(str(row.get("name")) for row in indexes.records),
    }


__all__ = [
    "GRAPH_NODE_LABEL",
    "NODE_KEY_CONSTRAINT",
    "apply_schema",
    "describe_schema",
    "node_labels",
]
