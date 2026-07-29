"""Rendering exported graphs ("IMPORT / EXPORT").

The four formats :mod:`app.importer.formats` reads, written back.

**Every writer round-trips through its own parser.** A test asserts
export-then-import reproduces the graph for all four, because an export
format that cannot be re-imported is a dead end -- and "snapshot
restore" depends on exactly that property holding.

**Exported Cypher is idempotent.** It uses ``MERGE`` on
``(key, organization_id)`` rather than ``CREATE``, so applying a dump
twice leaves one graph rather than two. A dump that doubles the graph
when re-run is worse than useless during a restore, which is precisely
when someone is likely to run it twice.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.graph.entities import GraphNode, GraphRelationship, Subgraph
from app.models.enums import GraphFormat

CONTENT_TYPES: dict[GraphFormat, str] = {
    GraphFormat.JSON: "application/json",
    GraphFormat.CSV: "text/csv; charset=utf-8",
    GraphFormat.GRAPHML: "application/xml",
    GraphFormat.CYPHER: "text/plain; charset=utf-8",
}

FILE_EXTENSIONS: dict[GraphFormat, str] = {
    GraphFormat.JSON: "json",
    GraphFormat.CSV: "csv",
    GraphFormat.GRAPHML: "graphml",
    GraphFormat.CYPHER: "cypher",
}

_CSV_COLUMNS = (
    "record_type",
    "key",
    "node_type",
    "name",
    "description",
    "project_id",
    "source",
    "from_key",
    "to_key",
    "relationship_type",
    "weight",
)


def write_json(subgraph: Subgraph) -> bytes:
    """Render as ``{"nodes": [...], "relationships": [...]}``."""
    document = {
        "nodes": [node.as_dict() for node in subgraph.nodes],
        "relationships": [edge.as_dict() for edge in subgraph.relationships],
        "node_count": len(subgraph.nodes),
        "relationship_count": len(subgraph.relationships),
    }
    return json.dumps(document, indent=2, sort_keys=True).encode("utf-8")


def write_csv(subgraph: Subgraph) -> bytes:
    """Render nodes and relationships into one CSV.

    One file with a ``record_type`` column rather than two, matching what
    :func:`app.importer.formats.parse_csv` reads -- two files is two
    chances to pair the wrong halves.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(_CSV_COLUMNS), extrasaction="ignore")
    writer.writeheader()
    for node in subgraph.nodes:
        writer.writerow(
            {
                "record_type": "node",
                "key": node.key,
                "node_type": node.node_type,
                "name": node.name,
                "description": node.description or "",
                "project_id": node.project_id or "",
                "source": node.source or "",
            }
        )
    for edge in subgraph.relationships:
        writer.writerow(
            {
                "record_type": "relationship",
                "from_key": edge.from_key,
                "to_key": edge.to_key,
                "relationship_type": edge.relationship_type,
                "weight": edge.weight,
            }
        )
    return buffer.getvalue().encode("utf-8")


def write_graphml(subgraph: Subgraph) -> bytes:
    """Render as GraphML.

    Built with ``ElementTree`` rather than string concatenation so node
    names containing ``&`` or ``<`` are escaped rather than producing a
    document no parser will read back.
    """
    root = ET.Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
    for name in ("node_type", "name", "description", "project_id", "source"):
        ET.SubElement(
            root,
            "key",
            {"id": name, "for": "node", "attr.name": name, "attr.type": "string"},
        )
    for name in ("relationship_type", "weight"):
        ET.SubElement(
            root,
            "key",
            {"id": name, "for": "edge", "attr.name": name, "attr.type": "string"},
        )

    graph = ET.SubElement(root, "graph", {"id": "G", "edgedefault": "directed"})
    for node in subgraph.nodes:
        element = ET.SubElement(graph, "node", {"id": node.key})
        _data(element, "node_type", node.node_type)
        _data(element, "name", node.name)
        _data(element, "description", node.description)
        _data(element, "project_id", node.project_id)
        _data(element, "source", node.source)
    for edge in subgraph.relationships:
        element = ET.SubElement(graph, "edge", {"source": edge.from_key, "target": edge.to_key})
        _data(element, "relationship_type", edge.relationship_type)
        _data(element, "weight", str(edge.weight))

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _data(parent: ET.Element, name: str, value: str | None) -> None:
    """Append a ``<data key="...">`` child when there is a value."""
    if value in (None, ""):
        return
    element = ET.SubElement(parent, "data", {"key": name})
    element.text = str(value)


def write_cypher(subgraph: Subgraph) -> bytes:
    """Render as idempotent Cypher.

    ``MERGE`` rather than ``CREATE``, so applying the dump twice leaves
    one graph. ``$organization_id`` is left as a parameter rather than
    baked in, which is what lets one export be restored into a different
    tenant deliberately -- and what stops an organization id being
    concatenated into a statement.
    """
    lines = [
        "// AI-IOS knowledge graph export",
        "// Apply with :param organization_id => '<uuid>' then run this file.",
        f"// {len(subgraph.nodes)} nodes, {len(subgraph.relationships)} relationships",
        "",
    ]
    for node in subgraph.nodes:
        properties = ", ".join(
            f"{name}: {_literal(value)}"
            for name, value in (
                ("key", node.key),
                ("node_type", node.node_type),
                ("name", node.name),
                ("description", node.description),
                ("project_id", node.project_id),
                ("source", node.source),
            )
            if value not in (None, "")
        )
        lines.append(
            f"MERGE (n:GraphNode:{node.node_type} "
            f"{{key: {_literal(node.key)}, organization_id: $organization_id}}) "
            f"SET n += {{{properties}}};"
        )
    lines.append("")
    for edge in subgraph.relationships:
        lines.append(
            f"MATCH (a:GraphNode {{key: {_literal(edge.from_key)}, "
            "organization_id: $organization_id}), "
            f"(b:GraphNode {{key: {_literal(edge.to_key)}, "
            "organization_id: $organization_id}) "
            f"MERGE (a)-[r:{edge.relationship_type}]->(b) "
            f"SET r.weight = {edge.weight};"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _literal(value: Any) -> str:
    """Render a Cypher string literal with quotes and backslashes escaped.

    Used only for **exported** statements, which are data this service
    produced, never a caller's input. Query construction elsewhere binds
    parameters instead -- see :mod:`app.cypher.builder`.
    """
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


WRITERS = {
    GraphFormat.JSON: write_json,
    GraphFormat.CSV: write_csv,
    GraphFormat.GRAPHML: write_graphml,
    GraphFormat.CYPHER: write_cypher,
}
"""Format to its writer, one per :class:`~app.models.enums.GraphFormat`."""


def render(subgraph: Subgraph, graph_format: GraphFormat) -> tuple[bytes, str, str]:
    """Render a subgraph; returns ``(payload, content_type, extension)``.

    Raises:
        ValidationError: If the format is unsupported.
    """
    writer = WRITERS.get(graph_format)
    if writer is None:
        supported = ", ".join(sorted(str(one) for one in WRITERS))
        raise ValidationError(
            f"Unsupported export format {str(graph_format)!r}. Supported: {supported}."
        )
    return (
        writer(subgraph),
        CONTENT_TYPES[graph_format],
        FILE_EXTENSIONS[graph_format],
    )


def build_subgraph(nodes: list[GraphNode], relationships: list[GraphRelationship]) -> Subgraph:
    """Assemble a subgraph for export."""
    return Subgraph(nodes=nodes, relationships=relationships)


__all__ = [
    "CONTENT_TYPES",
    "FILE_EXTENSIONS",
    "WRITERS",
    "build_subgraph",
    "render",
    "write_csv",
    "write_cypher",
    "write_graphml",
    "write_json",
]
