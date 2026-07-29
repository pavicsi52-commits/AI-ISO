"""Parsing imported graphs ("IMPORT / EXPORT").

Four formats, one output shape. Each parser turns bytes into
``(nodes, relationships, rejections)`` and **writes nothing** -- the
import service decides whether to persist. That separation is what makes
``dry_run`` real rather than a flag somebody has to remember to check.

**A bad row is rejected with a reason, never guessed at.** An import
that reports "900 imported" when the file had 1,000 rows has told you
nothing about the hundred that vanished, so every rejection carries the
row index and what was wrong with it.

**Cypher import is deliberately not "run the file".** Executing
arbitrary Cypher from an uploaded file is the same hole
``POST /graph/cypher`` spends three layers defending against, with the
extra property that nobody is watching. The parser extracts node and
relationship data from recognised ``CREATE``/``MERGE`` patterns and
discards everything else, so an uploaded ``DETACH DELETE`` is a
rejection rather than an execution.
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.graph.entities import NodeInput, RelationshipInput
from app.models.enums import GraphFormat, NodeType, RelationshipType

_NODE_PATTERN = re.compile(
    r"(?:CREATE|MERGE)\s*\(\s*\w*\s*:\s*(?:GraphNode\s*:\s*)?(\w+)\s*(\{[^}]*\})\s*\)",
    re.IGNORECASE,
)
_EDGE_PATTERN = re.compile(
    r"\(\s*\w*\s*\{[^}]*?key\s*:\s*['\"]([^'\"]+)['\"][^}]*?\}\s*\)"
    r"\s*-\s*\[\s*:\s*(\w+)[^\]]*\]\s*->\s*"
    r"\(\s*\w*\s*\{[^}]*?key\s*:\s*['\"]([^'\"]+)['\"][^}]*?\}\s*\)",
    re.IGNORECASE,
)
_PROPERTY_PATTERN = re.compile(r"(\w+)\s*:\s*(?:'([^']*)'|\"([^\"]*)\"|([^,}\s]+))")

_GRAPHML_NS = {"g": "http://graphml.graphdrawing.org/xmlns"}


@dataclass(slots=True)
class ParsedGraph:
    """What one parser produced from one payload."""

    nodes: list[NodeInput] = field(default_factory=list)
    relationships: list[RelationshipInput] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rejected(self) -> int:
        """How many rows could not be parsed."""
        return len(self.rejections)

    def check_coherent(self) -> None:
        """Drop edges whose endpoints are not in the payload.

        An edge pointing at a node the file never defines would either
        silently vanish at ``MATCH`` time or attach to an unrelated
        existing node with the same key. Rejecting it here, with a
        reason, is the honest outcome.
        """
        defined = {node.key for node in self.nodes}
        kept: list[RelationshipInput] = []
        for edge in self.relationships:
            missing = [key for key in (edge.from_key, edge.to_key) if key not in defined]
            if missing:
                self.rejections.append(
                    {
                        "reason": f"relationship endpoint not defined in payload: {missing}",
                        "from_key": edge.from_key,
                        "to_key": edge.to_key,
                    }
                )
                continue
            kept.append(edge)
        self.relationships = kept


def _reject(index: int, reason: str, detail: Any = None) -> dict[str, Any]:
    """Record why one row was refused."""
    return {"index": index, "reason": reason, "detail": detail}


def _node_from(
    raw: dict[str, Any], index: int, rejections: list[dict[str, Any]]
) -> NodeInput | None:
    """Build a node from a parsed row, recording why if it cannot."""
    key = raw.get("key") or raw.get("id")
    if not key:
        rejections.append(_reject(index, "node has no key"))
        return None
    raw_type = str(raw.get("node_type") or raw.get("type") or NodeType.CUSTOM_NODE)
    try:
        node_type = NodeType(raw_type)
    except ValueError:
        rejections.append(_reject(index, f"unknown node type {raw_type!r}", key))
        return None

    reserved = {"key", "id", "node_type", "type", "name", "description", "project_id", "source"}
    properties = {k: v for k, v in raw.items() if k not in reserved}
    try:
        return NodeInput(
            key=str(key),
            node_type=node_type,
            name=str(raw.get("name") or key),
            description=_optional(raw.get("description")),
            project_id=_optional(raw.get("project_id")),
            source=_optional(raw.get("source")),
            properties=properties,
        )
    except Exception as exc:
        rejections.append(_reject(index, f"invalid node: {exc}", key))
        return None


def _edge_from(
    raw: dict[str, Any], index: int, rejections: list[dict[str, Any]]
) -> RelationshipInput | None:
    """Build a relationship from a parsed row, recording why if it cannot."""
    from_key = raw.get("from_key") or raw.get("source") or raw.get("from")
    to_key = raw.get("to_key") or raw.get("target") or raw.get("to")
    if not from_key or not to_key:
        rejections.append(_reject(index, "relationship is missing an endpoint"))
        return None
    raw_type = str(raw.get("relationship_type") or raw.get("type") or "")
    try:
        edge_type = RelationshipType(raw_type)
    except ValueError:
        rejections.append(_reject(index, f"unknown relationship type {raw_type!r}"))
        return None
    try:
        return RelationshipInput(
            from_key=str(from_key),
            to_key=str(to_key),
            relationship_type=edge_type,
            weight=float(raw.get("weight", 1.0) or 1.0),
        )
    except Exception as exc:
        rejections.append(_reject(index, f"invalid relationship: {exc}"))
        return None


def _optional(value: Any) -> str | None:
    """Coerce to ``str``, keeping empty and ``None`` as ``None``."""
    return None if value in (None, "") else str(value)


def parse_json(payload: bytes) -> ParsedGraph:
    """Parse ``{"nodes": [...], "relationships": [...]}``.

    Raises:
        ValidationError: If the payload is not the expected JSON object.
    """
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValidationError("A JSON graph must be an object with nodes and relationships.")

    parsed = ParsedGraph()
    for index, raw in enumerate(document.get("nodes") or []):
        if not isinstance(raw, dict):
            parsed.rejections.append(_reject(index, "node is not an object"))
            continue
        node = _node_from(raw, index, parsed.rejections)
        if node is not None:
            parsed.nodes.append(node)
    for index, raw in enumerate(document.get("relationships") or []):
        if not isinstance(raw, dict):
            parsed.rejections.append(_reject(index, "relationship is not an object"))
            continue
        edge = _edge_from(raw, index, parsed.rejections)
        if edge is not None:
            parsed.relationships.append(edge)
    return parsed


def parse_csv(payload: bytes) -> ParsedGraph:
    """Parse a CSV of nodes and relationships in one file.

    A ``record_type`` column distinguishes them -- ``node`` or
    ``relationship``. One file rather than two because an import is one
    upload, and two files means two chances to pair the wrong halves.

    Raises:
        ValidationError: If the payload is not decodable CSV.
    """
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Not valid UTF-8 CSV: {exc}") from exc

    parsed = ParsedGraph()
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValidationError("The CSV has no header row.")

    for index, row in enumerate(reader):
        cleaned = {k: v for k, v in row.items() if k and v not in (None, "")}
        kind = str(cleaned.pop("record_type", "node")).lower()
        if kind == "relationship":
            edge = _edge_from(cleaned, index, parsed.rejections)
            if edge is not None:
                parsed.relationships.append(edge)
        elif kind == "node":
            node = _node_from(cleaned, index, parsed.rejections)
            if node is not None:
                parsed.nodes.append(node)
        else:
            parsed.rejections.append(_reject(index, f"unknown record_type {kind!r}"))
    return parsed


def parse_graphml(payload: bytes) -> ParsedGraph:
    """Parse GraphML ``<node>`` and ``<edge>`` elements.

    Raises:
        ValidationError: If the payload is not well-formed XML.
    """
    try:
        root = ET.fromstring(payload.decode("utf-8"))
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise ValidationError(f"Not valid GraphML: {exc}") from exc

    # ElementTree does not resolve external entities or DTDs, so the
    # billion-laughs and external-entity classes of XML attack do not
    # apply here. It is the right parser for this input.
    graph = root.find("g:graph", _GRAPHML_NS) or root.find("graph")
    if graph is None:
        raise ValidationError("The GraphML document has no <graph> element.")

    parsed = ParsedGraph()
    for index, element in enumerate(_find_all(graph, "node")):
        raw: dict[str, Any] = {"key": element.get("id")}
        raw.update(_graphml_data(element))
        node = _node_from(raw, index, parsed.rejections)
        if node is not None:
            parsed.nodes.append(node)

    for index, element in enumerate(_find_all(graph, "edge")):
        raw = {
            "from_key": element.get("source"),
            "to_key": element.get("target"),
        }
        raw.update(_graphml_data(element))
        edge = _edge_from(raw, index, parsed.rejections)
        if edge is not None:
            parsed.relationships.append(edge)
    return parsed


def _find_all(parent: ET.Element, tag: str) -> list[ET.Element]:
    """Find elements with or without the GraphML namespace.

    Real GraphML files come both ways -- exported by tools that declare
    the namespace and by tools that do not -- and refusing one of them
    would be a parser that only reads its own output.
    """
    found = parent.findall(f"g:{tag}", _GRAPHML_NS)
    return found or parent.findall(tag)


def _graphml_data(element: ET.Element) -> dict[str, Any]:
    """Collect ``<data key="...">`` children into a dict."""
    values: dict[str, Any] = {}
    for data in _find_all(element, "data"):
        name = data.get("key")
        if name:
            values[name] = data.text
    return values


def parse_cypher(payload: bytes) -> ParsedGraph:
    """Extract nodes and relationships from Cypher statements.

    **Parsed, not executed.** Running an uploaded Cypher file would hand
    an attacker exactly what ``POST /graph/cypher`` exists to prevent,
    with nobody watching. Recognised ``CREATE``/``MERGE`` node and
    relationship patterns are turned into data; everything else --
    including any write clause aimed at existing data -- is ignored and
    counted.

    Raises:
        ValidationError: If the payload is not decodable text.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Not valid UTF-8 Cypher: {exc}") from exc

    parsed = ParsedGraph()
    matched_spans = 0

    for index, match in enumerate(_NODE_PATTERN.finditer(text)):
        matched_spans += 1
        label, properties = match.group(1), match.group(2)
        raw = _cypher_properties(properties)
        raw.setdefault("node_type", label)
        node = _node_from(raw, index, parsed.rejections)
        if node is not None:
            parsed.nodes.append(node)

    for index, match in enumerate(_EDGE_PATTERN.finditer(text)):
        matched_spans += 1
        edge = _edge_from(
            {
                "from_key": match.group(1),
                "relationship_type": match.group(2),
                "to_key": match.group(3),
            },
            index,
            parsed.rejections,
        )
        if edge is not None:
            parsed.relationships.append(edge)

    statements = [one for one in text.split(";") if one.strip()]
    ignored = max(0, len(statements) - matched_spans)
    if ignored:
        parsed.rejections.append(
            {
                "reason": (
                    f"{ignored} statement(s) were not recognised as node or "
                    "relationship data and were ignored; this importer parses "
                    "Cypher, it does not execute it"
                ),
                "index": -1,
            }
        )
    return parsed


def _cypher_properties(block: str) -> dict[str, Any]:
    """Parse a ``{key: 'value', ...}`` property block."""
    values: dict[str, Any] = {}
    for match in _PROPERTY_PATTERN.finditer(block):
        name = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4)
        values[name] = value
    return values


PARSERS = {
    GraphFormat.JSON: parse_json,
    GraphFormat.CSV: parse_csv,
    GraphFormat.GRAPHML: parse_graphml,
    GraphFormat.CYPHER: parse_cypher,
}
"""Format to its parser.

Every :class:`~app.models.enums.GraphFormat` member has an entry, and a
test asserts that -- a format offered by the API with no parser would
fail at request time rather than at import time.
"""


def parse(payload: bytes, graph_format: GraphFormat) -> ParsedGraph:
    """Parse *payload* in *graph_format*.

    Raises:
        ValidationError: If the format is unsupported or the payload is
            malformed.
    """
    parser = PARSERS.get(graph_format)
    if parser is None:
        supported = ", ".join(sorted(str(one) for one in PARSERS))
        raise ValidationError(
            f"Unsupported import format {str(graph_format)!r}. Supported: {supported}."
        )
    parsed = parser(payload)
    parsed.check_coherent()
    return parsed


__all__ = [
    "PARSERS",
    "ParsedGraph",
    "parse",
    "parse_csv",
    "parse_cypher",
    "parse_graphml",
    "parse_json",
]
