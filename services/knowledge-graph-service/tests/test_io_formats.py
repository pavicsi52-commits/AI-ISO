"""Import and export formats, and that they round-trip.

**Every writer is tested against its own parser.** An export format
that cannot be re-imported is a dead end, and snapshot restore depends
on exactly that property holding -- so a round-trip test is not a nicety
here, it is the thing that makes restore trustworthy.

The Cypher importer gets extra attention because it is the one that
looks like it should execute the file and deliberately does not.
"""

from __future__ import annotations

import json

import pytest
from shared_core.exceptions.validation import ValidationError

from app.exporter.formats import (
    CONTENT_TYPES,
    FILE_EXTENSIONS,
    WRITERS,
    build_subgraph,
    render,
)
from app.graph.entities import GraphNode, GraphRelationship, Subgraph
from app.importer.formats import PARSERS, parse
from app.models.enums import GraphFormat, NodeType, RelationshipType


def node(key: str, node_type: NodeType = NodeType.APPLICATION, **extra: object) -> GraphNode:
    """A node for building test subgraphs."""
    return GraphNode(
        key=key,
        node_type=str(node_type),
        name=extra.pop("name", key),  # type: ignore[arg-type]
        organization_id="org",
        description=extra.pop("description", None),  # type: ignore[arg-type]
        source=extra.pop("source", None),  # type: ignore[arg-type]
        properties=dict(extra),
    )


def edge(
    source: str, target: str, edge_type: RelationshipType = RelationshipType.DEPENDS_ON
) -> GraphRelationship:
    """A relationship for building test subgraphs."""
    return GraphRelationship(
        from_key=source, to_key=target, relationship_type=str(edge_type), weight=1.0
    )


@pytest.fixture
def sample() -> Subgraph:
    """A small graph with every field a format has to carry."""
    return build_subgraph(
        [
            node("app-1", NodeType.APPLICATION, name="Billing", description="Bills people"),
            node("db-1", NodeType.DATABASE, name="billing-db", source="inventory"),
            node("vm-1", NodeType.VIRTUAL_MACHINE, name="vm-1"),
        ],
        [
            edge("app-1", "db-1"),
            edge("db-1", "vm-1", RelationshipType.RUNS_ON),
        ],
    )


class TestCoverage:
    """Every declared format has both halves."""

    def test_every_format_has_a_parser(self) -> None:
        # A format the API offers with no parser fails at request time
        # rather than at import time.
        assert set(PARSERS) == set(GraphFormat)

    def test_every_format_has_a_writer(self) -> None:
        assert set(WRITERS) == set(GraphFormat)

    def test_every_format_has_a_content_type_and_extension(self) -> None:
        assert set(CONTENT_TYPES) == set(GraphFormat)
        assert set(FILE_EXTENSIONS) == set(GraphFormat)


class TestRoundTrips:
    """Export then import reproduces the graph."""

    @pytest.mark.parametrize("graph_format", list(GraphFormat))
    def test_nodes_survive_a_round_trip(self, sample: Subgraph, graph_format: GraphFormat) -> None:
        payload, _content_type, _extension = render(sample, graph_format)
        parsed = parse(payload, graph_format)
        assert {n.key for n in parsed.nodes} == {n.key for n in sample.nodes}

    @pytest.mark.parametrize("graph_format", list(GraphFormat))
    def test_node_types_survive_a_round_trip(
        self, sample: Subgraph, graph_format: GraphFormat
    ) -> None:
        payload, _content_type, _extension = render(sample, graph_format)
        parsed = parse(payload, graph_format)
        by_key = {n.key: str(n.node_type) for n in parsed.nodes}
        assert by_key["app-1"] == "Application"
        assert by_key["db-1"] == "Database"

    @pytest.mark.parametrize("graph_format", list(GraphFormat))
    def test_relationships_survive_a_round_trip(
        self, sample: Subgraph, graph_format: GraphFormat
    ) -> None:
        payload, _content_type, _extension = render(sample, graph_format)
        parsed = parse(payload, graph_format)
        pairs = {(e.from_key, e.to_key, str(e.relationship_type)) for e in parsed.relationships}
        assert pairs == {
            ("app-1", "db-1", "DEPENDS_ON"),
            ("db-1", "vm-1", "RUNS_ON"),
        }

    @pytest.mark.parametrize("graph_format", list(GraphFormat))
    def test_an_empty_graph_round_trips(self, graph_format: GraphFormat) -> None:
        payload, _content_type, _extension = render(Subgraph(), graph_format)
        parsed = parse(payload, graph_format)
        assert parsed.nodes == []
        assert parsed.relationships == []


class TestJson:
    """The default, and the snapshot format."""

    def test_the_document_shape(self, sample: Subgraph) -> None:
        payload, content_type, extension = render(sample, GraphFormat.JSON)
        document = json.loads(payload)
        assert content_type == "application/json"
        assert extension == "json"
        assert document["node_count"] == 3
        assert document["relationship_count"] == 2

    def test_a_non_object_document_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must be an object"):
            parse(b"[1, 2, 3]", GraphFormat.JSON)

    def test_malformed_json_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Not valid JSON"):
            parse(b"{not json", GraphFormat.JSON)

    def test_a_node_without_a_key_is_rejected_with_a_reason(self) -> None:
        parsed = parse(json.dumps({"nodes": [{"name": "nameless"}]}).encode(), GraphFormat.JSON)
        assert parsed.nodes == []
        assert parsed.rejected == 1
        assert "no key" in parsed.rejections[0]["reason"]

    def test_an_unknown_node_type_is_rejected(self) -> None:
        parsed = parse(
            json.dumps({"nodes": [{"key": "a", "node_type": "Sorcery"}]}).encode(),
            GraphFormat.JSON,
        )
        assert parsed.nodes == []
        assert "unknown node type" in parsed.rejections[0]["reason"]

    def test_an_unknown_relationship_type_is_rejected(self) -> None:
        parsed = parse(
            json.dumps(
                {
                    "nodes": [{"key": "a"}, {"key": "b"}],
                    "relationships": [
                        {"from_key": "a", "to_key": "b", "relationship_type": "CURSES"}
                    ],
                }
            ).encode(),
            GraphFormat.JSON,
        )
        assert parsed.relationships == []
        assert "unknown relationship type" in parsed.rejections[0]["reason"]

    def test_a_non_object_row_is_rejected(self) -> None:
        parsed = parse(json.dumps({"nodes": ["just a string"]}).encode(), GraphFormat.JSON)
        assert "not an object" in parsed.rejections[0]["reason"]


class TestCoherence:
    """Edges must point at nodes the payload defines."""

    def test_an_edge_to_an_undefined_node_is_rejected(self) -> None:
        # It would either vanish at MATCH time or attach to an unrelated
        # existing node with the same key. Neither is acceptable
        # silently.
        parsed = parse(
            json.dumps(
                {
                    "nodes": [{"key": "a"}],
                    "relationships": [
                        {
                            "from_key": "a",
                            "to_key": "elsewhere",
                            "relationship_type": "DEPENDS_ON",
                        }
                    ],
                }
            ).encode(),
            GraphFormat.JSON,
        )
        assert parsed.relationships == []
        assert "not defined in payload" in parsed.rejections[0]["reason"]

    def test_a_self_loop_in_a_payload_is_one_rejection(self) -> None:
        # Not an aborted batch -- the rule lives on the model, so the
        # parser catches it per row.
        parsed = parse(
            json.dumps(
                {
                    "nodes": [{"key": "a"}],
                    "relationships": [
                        {"from_key": "a", "to_key": "a", "relationship_type": "DEPENDS_ON"}
                    ],
                }
            ).encode(),
            GraphFormat.JSON,
        )
        assert parsed.nodes != []
        assert parsed.relationships == []
        assert parsed.rejected >= 1


class TestCsv:
    """One file, two record types."""

    def test_the_header_and_records(self, sample: Subgraph) -> None:
        payload, content_type, extension = render(sample, GraphFormat.CSV)
        text = payload.decode()
        assert content_type.startswith("text/csv")
        assert extension == "csv"
        assert text.splitlines()[0].startswith("record_type,")
        assert text.count("\nnode,") == 3
        assert text.count("\nrelationship,") == 2

    def test_a_csv_with_no_header_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no header row"):
            parse(b"", GraphFormat.CSV)

    def test_an_unknown_record_type_is_rejected(self) -> None:
        parsed = parse(b"record_type,key,node_type\nspaceship,a,Application\n", GraphFormat.CSV)
        assert "unknown record_type" in parsed.rejections[0]["reason"]

    def test_a_row_without_a_record_type_defaults_to_node(self) -> None:
        parsed = parse(b"key,node_type,name\na,Application,A\n", GraphFormat.CSV)
        assert [n.key for n in parsed.nodes] == ["a"]

    def test_undecodable_bytes_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="Not valid UTF-8"):
            parse(b"\xff\xfe\x00binary", GraphFormat.CSV)


class TestGraphml:
    """XML, with escaping that survives a round trip."""

    def test_a_name_with_xml_metacharacters_survives(self) -> None:
        # Built with ElementTree rather than string concatenation, so an
        # ampersand does not produce a document no parser will read back.
        awkward = build_subgraph(
            [node("a", name="Fish & Chips <html>")],
            [],
        )
        payload, _content_type, _extension = render(awkward, GraphFormat.GRAPHML)
        parsed = parse(payload, GraphFormat.GRAPHML)
        assert parsed.nodes[0].name == "Fish & Chips <html>"

    def test_malformed_xml_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Not valid GraphML"):
            parse(b"<graphml><unclosed>", GraphFormat.GRAPHML)

    def test_a_document_without_a_graph_element_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no <graph> element"):
            parse(b"<graphml></graphml>", GraphFormat.GRAPHML)

    def test_a_namespaceless_document_is_read(self) -> None:
        # Real GraphML arrives both ways; refusing one would be a parser
        # that only reads its own output.
        payload = (
            b'<graphml><graph id="G" edgedefault="directed">'
            b'<node id="a"><data key="node_type">Application</data></node>'
            b"</graph></graphml>"
        )
        parsed = parse(payload, GraphFormat.GRAPHML)
        assert [n.key for n in parsed.nodes] == ["a"]


class TestCypherImport:
    """Parsed, never executed."""

    def test_exported_cypher_uses_merge_not_create(self, sample: Subgraph) -> None:
        # Applying a dump twice must leave one graph. A dump that doubles
        # the graph on re-run is worst precisely during a restore, which
        # is when someone is most likely to run it twice.
        payload, _content_type, _extension = render(sample, GraphFormat.CYPHER)
        text = payload.decode()
        assert "MERGE (" in text
        assert "CREATE (" not in text

    def test_the_organization_is_left_as_a_parameter(self, sample: Subgraph) -> None:
        # Which is what lets one export be restored into a different
        # tenant deliberately, and what stops an id being concatenated in.
        payload, _content_type, _extension = render(sample, GraphFormat.CYPHER)
        assert b"$organization_id" in payload

    def test_a_destructive_statement_is_ignored_not_run(self) -> None:
        # Running an uploaded Cypher file would hand an attacker exactly
        # what POST /graph/cypher spends three layers preventing, with
        # nobody watching.
        parsed = parse(b"MATCH (n) DETACH DELETE n;", GraphFormat.CYPHER)
        assert parsed.nodes == []
        assert parsed.relationships == []
        assert any("not recognised" in one["reason"] for one in parsed.rejections)

    def test_recognised_node_statements_become_data(self) -> None:
        payload = b"MERGE (n:GraphNode:Application {key: 'app-1', name: 'Billing'});"
        parsed = parse(payload, GraphFormat.CYPHER)
        assert [n.key for n in parsed.nodes] == ["app-1"]
        assert parsed.nodes[0].name == "Billing"

    def test_a_quoted_apostrophe_survives_export(self) -> None:
        awkward = build_subgraph([node("a", name="Bob's Server")], [])
        payload, _content_type, _extension = render(awkward, GraphFormat.CYPHER)
        assert b"Bob\\'s Server" in payload

    def test_undecodable_bytes_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="Not valid UTF-8"):
            parse(b"\xff\xfe MERGE", GraphFormat.CYPHER)


class TestDispatch:
    """Choosing a format."""

    def test_an_unsupported_import_format_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported import format"):
            parse(b"{}", "parquet")  # type: ignore[arg-type]

    def test_an_unsupported_export_format_is_refused(self, sample: Subgraph) -> None:
        with pytest.raises(ValidationError, match="Unsupported export format"):
            render(sample, "parquet")  # type: ignore[arg-type]
