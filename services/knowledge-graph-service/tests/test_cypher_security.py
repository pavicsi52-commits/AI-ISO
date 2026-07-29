"""The Cypher injection boundary.

This is the most security-relevant file in the service, so it is
deliberately paranoid. Three things cannot be bound parameters in
Cypher -- labels, relationship types, and variable-length ranges -- and
every one of them is validated against a closed vocabulary before any
string formatting. These tests exist to make sure that stays true.

The guard tests are structured around **what an attacker would
actually try**: a write clause, a write hidden in a comment, a keyword
buried in a string, a procedure that executes generated Cypher, and an
unparameterised literal that turns a filter into a full scan.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.validation import ValidationError

from app.cypher import guard
from app.cypher.builder import (
    MAX_DEPTH_CEILING,
    label_clause,
    node_match,
    order_clause,
    relationship_clause,
    traversal_pattern,
    validate_depth,
    validate_label,
    validate_limit,
    validate_property_name,
    validate_relationship_type,
    validate_relationship_types,
)
from app.models.enums import NodeType, RelationshipType, TraversalDirection


class TestLabelValidation:
    """Labels are query text, so an unknown one is refused."""

    @pytest.mark.parametrize("node_type", list(NodeType))
    def test_every_declared_node_type_is_accepted(self, node_type: NodeType) -> None:
        assert validate_label(node_type) == str(node_type)

    @pytest.mark.parametrize(
        "attempt",
        [
            "Application) DETACH DELETE n //",
            "GraphNode`) MATCH (x) DELETE x //",
            "Application|Secret",
            "",
            "application",  # correct spelling, wrong case
            "n:Application",
        ],
    )
    def test_anything_outside_the_vocabulary_is_refused(self, attempt: str) -> None:
        # A label cannot be escaped into safety -- it is part of the
        # query text -- so the only safe answer is a closed vocabulary.
        with pytest.raises(ValidationError, match="Unknown node label"):
            validate_label(attempt)

    def test_the_refusal_names_the_escape_hatch(self) -> None:
        with pytest.raises(ValidationError, match="CustomNode"):
            validate_label("SomethingBespoke")


class TestRelationshipTypeValidation:
    """Relationship types are query text too."""

    @pytest.mark.parametrize("edge_type", list(RelationshipType))
    def test_every_declared_type_is_accepted(self, edge_type: RelationshipType) -> None:
        assert validate_relationship_type(edge_type) == str(edge_type)

    @pytest.mark.parametrize(
        "attempt",
        ["DEPENDS_ON]->() DETACH DELETE n //", "depends_on", "*", "DEPENDS_ON|SECRET"],
    )
    def test_anything_outside_the_vocabulary_is_refused(self, attempt: str) -> None:
        with pytest.raises(ValidationError, match="Unknown relationship type"):
            validate_relationship_type(attempt)

    def test_an_empty_list_means_any_relationship(self) -> None:
        # An unfiltered pattern, not a pattern built from unvalidated
        # input -- those are different things.
        assert validate_relationship_types(None) == []
        assert validate_relationship_types([]) == []


class TestDepthValidation:
    """Depth is the one number formatted into query text."""

    def test_a_valid_depth_passes_through(self) -> None:
        assert validate_depth(3, ceiling=6) == 3

    @pytest.mark.parametrize("depth", [0, -1, 7])
    def test_out_of_range_is_refused(self, depth: int) -> None:
        with pytest.raises(ValidationError, match="between 1 and"):
            validate_depth(depth, ceiling=6)

    def test_a_boolean_is_not_an_integer_here(self) -> None:
        # bool subclasses int, so an unguarded isinstance check would let
        # True through as depth 1.
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_depth(True, ceiling=6)  # type: ignore[arg-type]

    @pytest.mark.parametrize("depth", ["3", 3.0, None, [3]])
    def test_a_non_integer_is_refused(self, depth: object) -> None:
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_depth(depth, ceiling=6)  # type: ignore[arg-type]

    def test_the_hard_ceiling_beats_a_larger_configured_one(self) -> None:
        # A configured ceiling can be lowered but never raised past the
        # hard bound, because traversal cost grows exponentially.
        with pytest.raises(ValidationError, match=f"between 1 and {MAX_DEPTH_CEILING}"):
            validate_depth(MAX_DEPTH_CEILING + 1, ceiling=1_000)


class TestLimitValidation:
    """Limits are bound, but still range-checked."""

    def test_a_valid_limit_passes(self) -> None:
        assert validate_limit(50, ceiling=1_000) == 50

    @pytest.mark.parametrize("limit", [0, -5, 1_001])
    def test_out_of_range_is_refused(self, limit: int) -> None:
        with pytest.raises(ValidationError, match="between 1 and"):
            validate_limit(limit, ceiling=1_000)

    def test_a_boolean_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_limit(True, ceiling=1_000)  # type: ignore[arg-type]


class TestPropertyNameValidation:
    """Property names appear in ORDER BY, so they are identifiers."""

    @pytest.mark.parametrize("name", ["name", "node_type", "_private", "a1"])
    def test_a_valid_identifier_passes(self, name: str) -> None:
        assert validate_property_name(name) == name

    @pytest.mark.parametrize(
        "attempt",
        ["name DESC, n.secret", "n.name", "na me", "`name`", "1name", "", "name;"],
    )
    def test_anything_that_could_close_an_identifier_is_refused(self, attempt: str) -> None:
        with pytest.raises(ValidationError, match="not a valid identifier"):
            validate_property_name(attempt)


class TestPatternConstruction:
    """The rendered fragments, and that they carry no injected text."""

    def test_a_label_clause_joins_validated_labels(self) -> None:
        clause = label_clause([NodeType.APPLICATION, NodeType.DATABASE])
        assert clause == ":Application|Database"

    def test_no_labels_matches_any_node(self) -> None:
        assert label_clause(None) == ""
        assert label_clause([]) == ""

    def test_a_relationship_clause_can_be_variable_length(self) -> None:
        clause = relationship_clause([RelationshipType.DEPENDS_ON], depth=3, ceiling=6)
        assert clause == "r:DEPENDS_ON*1..3"

    def test_direction_is_the_whole_distinction(self) -> None:
        # Getting this backwards answers "who breaks if I go down?" with
        # "what do I need?" -- confidently, and wrongly.
        outgoing = traversal_pattern(direction=TraversalDirection.OUTGOING)
        incoming = traversal_pattern(direction=TraversalDirection.INCOMING)
        both = traversal_pattern(direction=TraversalDirection.BOTH)
        assert outgoing == "-[r]->"
        assert incoming == "<-[r]-"
        assert both == "-[r]-"

    def test_an_unknown_direction_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported traversal direction"):
            traversal_pattern(direction="sideways")  # type: ignore[arg-type]

    def test_a_node_match_always_scopes_to_an_organization(self) -> None:
        # Tenant isolation lives in the pattern itself, bound as a
        # parameter, so a query that forgets it does not compile into
        # something that reads another tenant's graph.
        pattern = node_match(labels=[NodeType.APPLICATION])
        assert "organization_id: $organization_id" in pattern
        assert ":Application" in pattern

    def test_a_node_match_can_bind_a_key(self) -> None:
        pattern = node_match(key_parameter="root_key")
        assert "key: $root_key" in pattern
        assert "organization_id: $organization_id" in pattern

    def test_an_order_clause_validates_its_property(self) -> None:
        assert order_clause("n", "name") == " ORDER BY n.name ASC"
        assert order_clause("n", "name", descending=True) == " ORDER BY n.name DESC"
        assert order_clause("n", None) == ""
        with pytest.raises(ValidationError):
            order_clause("n", "name; DROP")


class TestCypherGuardWrites:
    """Write clauses are refused, whatever shape they arrive in."""

    @pytest.mark.parametrize(
        "statement",
        [
            "MATCH (n) DETACH DELETE n",
            "MATCH (n) DELETE n",
            "CREATE (n:GraphNode {key: $k})",
            "MERGE (n:GraphNode {key: $k})",
            "MATCH (n) SET n.owner = $who",
            "MATCH (n) REMOVE n.owner",
            "DROP INDEX graph_node_search",
            "MATCH (n) FOREACH (x IN $items | SET n.tag = x)",
            "LOAD CSV FROM $url AS row RETURN row",
        ],
    )
    def test_every_write_clause_is_denied(self, statement: str) -> None:
        result = guard.inspect(statement)
        assert not result.allowed
        assert "read-only" in (result.reason or "")

    def test_a_write_hidden_in_a_comment_is_still_seen(self) -> None:
        # Comments are stripped before the keyword scan, so a write
        # cannot hide inside one -- and equally, a comment mentioning
        # DELETE does not make an innocent query fail. This asserts the
        # first half; the string test below asserts the second.
        assert guard.inspect("MATCH (n) /* fine */ DETACH DELETE n").allowed is False

    def test_a_keyword_inside_a_string_is_not_a_write(self) -> None:
        # String contents are blanked, so RETURN 'please DELETE this' is
        # a projection, not a deletion.
        result = guard.inspect(
            "MATCH (n {organization_id: $org}) RETURN 'please DELETE this' AS note"
        )
        assert result.allowed, result.reason

    def test_a_comment_mentioning_a_write_does_not_block_a_read(self) -> None:
        result = guard.inspect(
            "MATCH (n {organization_id: $org}) // we never DELETE here\nRETURN n.key"
        )
        assert result.allowed, result.reason

    def test_case_does_not_matter(self) -> None:
        assert not guard.inspect("match (n) detach delete n").allowed


class TestCypherGuardProcedures:
    """Procedures that write or execute generated Cypher are refused."""

    @pytest.mark.parametrize(
        "statement",
        [
            "CALL apoc.cypher.run($q, {}) YIELD value RETURN value",
            "CALL apoc.cypher.doIt($q, {}) YIELD value RETURN value",
            "CALL apoc.create.node($labels, $props) YIELD node RETURN node",
            "CALL apoc.periodic.iterate($a, $b, {}) YIELD batches RETURN batches",
            "CALL apoc.load.json($url) YIELD value RETURN value",
            "CALL apoc.export.csv.all($file, {}) YIELD file RETURN file",
            "CALL dbms.security.listUsers() YIELD username RETURN username",
            "CALL apoc.trigger.add($name, $stmt, {}) YIELD name RETURN name",
        ],
    )
    def test_forbidden_namespaces_are_denied(self, statement: str) -> None:
        result = guard.inspect(statement)
        assert not result.allowed
        assert "not permitted" in (result.reason or "")

    def test_apoc_cypher_run_matters_most(self) -> None:
        # It executes a Cypher string built at runtime, which would let a
        # read-only statement smuggle a write past every other check.
        result = guard.inspect("CALL apoc.cypher.run($q, $params) YIELD value RETURN value")
        assert "apoc.cypher.run" in (result.reason or "")

    def test_a_harmless_procedure_is_allowed(self) -> None:
        result = guard.inspect(
            "CALL db.index.fulltext.queryNodes($index, $term) YIELD node "
            "WHERE node.organization_id = $org RETURN node.key"
        )
        assert result.allowed, result.reason


class TestCypherGuardParameters:
    """Every value must be bound, not written into the text."""

    @pytest.mark.parametrize(
        "statement",
        [
            "MATCH (n) RETURN n LIMIT 100",
            "MATCH (n) WHERE n.port = 8080 RETURN n",
            "MATCH (n) RETURN n SKIP 500",
        ],
    )
    def test_a_bare_number_is_refused(self, statement: str) -> None:
        # Allowing LIMIT 100 means allowing SKIP 999999 and every other
        # unparameterised value; the endpoint applies its own limit, so
        # a caller never needs one.
        result = guard.inspect(statement)
        assert not result.allowed
        assert "bound parameter" in (result.reason or "")

    @pytest.mark.parametrize(
        "statement",
        [
            "MATCH (n)-[r*1..3]-(m) RETURN m.key",
            "MATCH (n)-[*]-(m) RETURN m.key",
            "MATCH p = (a)-[r:DEPENDS_ON*1..50]->(b) RETURN p",
            "MATCH (n)-[r*2..]-(m) RETURN m.key",
        ],
    )
    def test_a_variable_length_range_is_refused(self, statement: str) -> None:
        # Found by this suite: the numeric-literal scan cannot see the
        # bounds inside [*1..3], because 1 is followed by a dot and 3 is
        # preceded by one. A read-only statement could therefore ask for
        # [*1..50] and pin the database. Cypher cannot bind a range as a
        # parameter, so there is no safe caller-authored form -- the
        # bounded traversal endpoints are the supported path.
        result = guard.inspect(statement)
        assert not result.allowed
        assert "Variable-length" in (result.reason or "")
        assert "/graph/topology" in (result.reason or "")

    def test_a_fully_parameterised_read_is_allowed(self) -> None:
        result = guard.inspect(
            "MATCH (n:GraphNode {organization_id: $organization_id}) "
            "WHERE n.node_type = $node_type RETURN n.key AS key LIMIT $limit"
        )
        assert result.allowed, result.reason
        assert result.parameters_used == {"organization_id", "node_type", "limit"}

    def test_an_empty_statement_is_refused(self) -> None:
        assert not guard.inspect("").allowed
        assert not guard.inspect("   \n  ").allowed

    def test_require_read_only_raises_with_the_specific_reason(self) -> None:
        with pytest.raises(ValidationError, match="DELETE"):
            guard.require_read_only("MATCH (n) DELETE n")

    def test_missing_parameters_are_named(self) -> None:
        # An unbound parameter is null in Cypher, and a filter comparing
        # against null silently matches nothing -- an empty result that
        # looks like a real answer.
        with pytest.raises(ValidationError, match="not supplied: node_type"):
            guard.require_bound_parameters(
                "MATCH (n {organization_id: $organization_id}) "
                "WHERE n.node_type = $node_type RETURN n",
                {"organization_id": "x"},
            )

    def test_supplying_every_parameter_passes(self) -> None:
        guard.require_bound_parameters(
            "MATCH (n {organization_id: $organization_id}) RETURN n",
            {"organization_id": "x"},
        )


class TestGuardInternals:
    """The lexical machinery the classification rests on."""

    def test_strip_noise_blanks_strings_and_removes_comments(self) -> None:
        cleaned = guard.strip_noise(
            "MATCH (n) // a comment\n WHERE n.name = 'DELETE me' /* block */ RETURN n"
        )
        assert "comment" not in cleaned
        assert "block" not in cleaned
        assert "DELETE me" not in cleaned
        assert "MATCH" in cleaned and "RETURN" in cleaned

    def test_a_guard_result_is_truthy_when_allowed(self) -> None:
        assert bool(guard.inspect("MATCH (n {organization_id: $org}) RETURN n"))
        assert not bool(guard.inspect("MATCH (n) DELETE n"))

    def test_every_write_clause_constant_is_upper_case(self) -> None:
        # The scan upper-cases each word before comparing, so a
        # lower-case entry in the set would never match anything.
        assert all(clause.isupper() for clause in guard.WRITE_CLAUSES)

    def test_every_forbidden_procedure_is_lower_case(self) -> None:
        # The procedure check lower-cases the statement, so an
        # upper-case entry would never match.
        assert all(one.islower() for one in guard.FORBIDDEN_PROCEDURES)
