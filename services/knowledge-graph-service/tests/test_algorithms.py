"""Graph algorithms, on graphs whose answers are known by hand.

Every fixture here is small enough to verify by inspection, which is
the point: an algorithm test on a random graph can only assert that the
code did *something*. A five-node graph with one obvious chokepoint can
assert it found the chokepoint.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.validation import ValidationError

from app.analytics.algorithms import (
    Graph,
    betweenness_centrality,
    community_detection,
    connected_components,
    critical_assets,
    degree_centrality,
    in_degree,
    out_degree,
    pagerank,
    relationship_density,
    require_size,
    risk_propagation,
    shortest_path_length,
)
from app.dependencies.engine import (
    DISTANCE_DECAY,
    AffectedNode,
    AnalysisResult,
    build_adjacency,
    dependency_score,
    score_affected,
)
from app.graph.entities import GraphNode, GraphRelationship, Subgraph
from app.models.enums import TraversalDirection


def node(key: str, node_type: str = "Application") -> GraphNode:
    """A minimal node for building test subgraphs."""
    return GraphNode(key=key, node_type=node_type, name=key, organization_id="org")


def edge(source: str, target: str, weight: float = 1.0) -> GraphRelationship:
    """A minimal relationship for building test subgraphs."""
    return GraphRelationship(
        from_key=source, to_key=target, relationship_type="DEPENDS_ON", weight=weight
    )


@pytest.fixture
def chain() -> Graph:
    """``a -> b -> c -> d``. Every interior node is a chokepoint."""
    return Graph.from_subgraph(
        Subgraph(
            nodes=[node(k) for k in "abcd"],
            relationships=[edge("a", "b"), edge("b", "c"), edge("c", "d")],
        )
    )


@pytest.fixture
def star() -> Graph:
    """A hub with four spokes. The hub is on every path."""
    return Graph.from_subgraph(
        Subgraph(
            nodes=[node(k) for k in ("hub", "s1", "s2", "s3", "s4")],
            relationships=[edge("hub", f"s{index}") for index in range(1, 5)],
        )
    )


@pytest.fixture
def split() -> Graph:
    """Two triangles with no edge between them: two components."""
    return Graph.from_subgraph(
        Subgraph(
            nodes=[node(k) for k in ("a", "b", "c", "x", "y", "z")],
            relationships=[
                edge("a", "b"),
                edge("b", "c"),
                edge("c", "a"),
                edge("x", "y"),
                edge("y", "z"),
                edge("z", "x"),
            ],
        )
    )


class TestGraphIndex:
    """The adjacency view every algorithm starts from."""

    def test_counts_match_the_subgraph(self, chain: Graph) -> None:
        assert chain.node_count == 4
        assert chain.edge_count == 3

    def test_an_edge_to_a_node_outside_the_subgraph_is_dropped(self) -> None:
        # Otherwise every measure would disagree with the node list it
        # is reported against.
        graph = Graph.from_subgraph(
            Subgraph(nodes=[node("a")], relationships=[edge("a", "elsewhere")])
        )
        assert graph.node_count == 1
        assert graph.edge_count == 0

    def test_an_isolated_node_is_kept(self) -> None:
        # It scores zero on every centrality measure, which is the
        # correct answer and a different statement from "not present".
        graph = Graph.from_subgraph(Subgraph(nodes=[node("lonely")], relationships=[]))
        assert graph.node_count == 1
        assert degree_centrality(graph) == {"lonely": 0.0}

    def test_an_empty_graph_is_handled(self) -> None:
        graph = Graph.from_subgraph(Subgraph())
        assert graph.node_count == 0
        assert degree_centrality(graph) == {}
        assert pagerank(graph) == {}
        assert connected_components(graph) == []
        assert relationship_density(graph) == 0.0


class TestDegree:
    """Degree centrality and its directed breakdowns."""

    def test_the_hub_has_the_highest_degree(self, star: Graph) -> None:
        scores = degree_centrality(star, normalise=False)
        assert scores["hub"] == 4
        assert all(scores[f"s{index}"] == 1 for index in range(1, 5))

    def test_normalisation_bounds_it_to_one(self, star: Graph) -> None:
        scores = degree_centrality(star)
        assert scores["hub"] == 1.0  # connected to all four others

    def test_direction_is_distinguished(self, chain: Graph) -> None:
        # "how many depend on me" and "how many do I depend on" are
        # different questions; a node nothing points at cannot break
        # anything else.
        assert in_degree(chain) == {"a": 0, "b": 1, "c": 1, "d": 1}
        assert out_degree(chain) == {"a": 1, "b": 1, "c": 1, "d": 0}


class TestBetweenness:
    """The chokepoint finder."""

    def test_interior_chain_nodes_score_and_ends_do_not(self, chain: Graph) -> None:
        scores = betweenness_centrality(chain, normalise=False)
        assert scores["b"] > 0
        assert scores["c"] > 0
        assert scores["a"] == 0
        assert scores["d"] == 0

    def test_a_hub_is_found_that_degree_alone_would_miss(self) -> None:
        # The bridge has only two connections, so a degree count ranks it
        # joint-lowest -- and it is the single point of failure.
        graph = Graph.from_subgraph(
            Subgraph(
                nodes=[node(k) for k in ("a", "b", "bridge", "y", "z")],
                relationships=[
                    edge("a", "b"),
                    edge("b", "bridge"),
                    edge("bridge", "y"),
                    edge("y", "z"),
                ],
            )
        )
        between = betweenness_centrality(graph)
        degrees = degree_centrality(graph, normalise=False)
        assert max(between, key=lambda k: between[k]) == "bridge"
        assert degrees["bridge"] == 2  # not the highest degree

    def test_a_graph_too_small_for_intermediaries_scores_zero(self) -> None:
        graph = Graph.from_subgraph(
            Subgraph(nodes=[node("a"), node("b")], relationships=[edge("a", "b")])
        )
        assert set(betweenness_centrality(graph).values()) == {0.0}


class TestPageRank:
    """Importance by incoming links."""

    def test_ranks_sum_to_about_one(self, chain: Graph) -> None:
        # Dangling nodes have their rank redistributed; without that the
        # ranks stop summing to 1 and become incomparable between runs.
        ranks = pagerank(chain)
        assert sum(ranks.values()) == pytest.approx(1.0, abs=0.01)

    def test_the_end_of_a_chain_ranks_highest(self, chain: Graph) -> None:
        # Run on incoming edges, so a node many important things depend
        # on scores highly -- the infrastructure reading of importance.
        ranks = pagerank(chain)
        assert max(ranks, key=lambda k: ranks[k]) == "d"

    def test_it_converges_and_stops(self, star: Graph) -> None:
        # A converged run and a much longer one agree, which is what the
        # tolerance check is for.
        short = pagerank(star, iterations=5)
        long = pagerank(star, iterations=100)
        for key in short:
            assert short[key] == pytest.approx(long[key], abs=0.01)

    def test_damping_changes_the_distribution(self, chain: Graph) -> None:
        assert pagerank(chain, damping=0.5) != pagerank(chain, damping=0.95)


class TestComponentsAndCommunities:
    """Structure, not importance."""

    def test_two_triangles_are_two_components(self, split: Graph) -> None:
        components = connected_components(split)
        assert len(components) == 2
        assert all(len(one) == 3 for one in components)

    def test_components_are_largest_first(self) -> None:
        graph = Graph.from_subgraph(
            Subgraph(
                nodes=[node(k) for k in ("a", "b", "c", "z")],
                relationships=[edge("a", "b"), edge("b", "c")],
            )
        )
        components = connected_components(graph)
        assert len(components[0]) == 3
        assert components[1] == ["z"]

    def test_community_detection_is_deterministic(self, split: Graph) -> None:
        # The usual randomised form gives different communities on every
        # run, and an operator comparing today to yesterday needs them to
        # mean the same thing.
        first = community_detection(split)
        second = community_detection(split)
        assert first == second

    def test_two_triangles_land_in_two_communities(self, split: Graph) -> None:
        communities = community_detection(split)
        assert communities["a"] == communities["b"] == communities["c"]
        assert communities["x"] == communities["y"] == communities["z"]
        assert communities["a"] != communities["x"]

    def test_community_zero_is_the_largest(self) -> None:
        graph = Graph.from_subgraph(
            Subgraph(
                nodes=[node(k) for k in ("a", "b", "c", "y", "z")],
                relationships=[edge("a", "b"), edge("b", "c"), edge("y", "z")],
            )
        )
        communities = community_detection(graph)
        sizes: dict[int, int] = {}
        for label in communities.values():
            sizes[label] = sizes.get(label, 0) + 1
        assert sizes[0] >= sizes.get(1, 0)


class TestDensityAndPaths:
    """Cheap structural measures."""

    def test_density_of_a_sparse_graph_is_small(self, chain: Graph) -> None:
        # 3 edges of a possible 12.
        assert relationship_density(chain) == pytest.approx(0.25)

    def test_density_needs_at_least_two_nodes(self) -> None:
        graph = Graph.from_subgraph(Subgraph(nodes=[node("a")]))
        assert relationship_density(graph) == 0.0

    def test_shortest_path_counts_hops(self, chain: Graph) -> None:
        assert shortest_path_length(chain, source="a", target="d") == 3
        assert shortest_path_length(chain, source="a", target="a") == 0

    def test_unconnected_nodes_return_none(self, split: Graph) -> None:
        # None rather than infinity or -1: "not connected" is a real
        # answer, and a sentinel number invites arithmetic on it.
        assert shortest_path_length(split, source="a", target="x") is None

    def test_an_unknown_source_returns_none(self, chain: Graph) -> None:
        assert shortest_path_length(chain, source="ghost", target="a") is None


class TestCriticalAssets:
    """Topology blended with what an operator declared."""

    def test_the_hub_is_critical_on_topology_alone(self, star: Graph) -> None:
        ranked = critical_assets(star)
        assert ranked[0]["key"] == "hub"

    def test_a_declared_critical_node_is_promoted(self, star: Graph) -> None:
        # Nothing computed from topology can know that a structurally
        # peripheral node is the one thing the business cannot lose.
        plain = critical_assets(star)
        weighted = critical_assets(star, criticality={"s1": 1.0})
        plain_rank = [one["key"] for one in plain].index("s1")
        weighted_rank = [one["key"] for one in weighted].index("s1")
        assert weighted_rank < plain_rank

    def test_every_entry_carries_its_components(self, star: Graph) -> None:
        # A bare score nobody can decompose is a number people stop
        # trusting.
        entry = critical_assets(star)[0]
        assert set(entry) == {
            "key",
            "score",
            "pagerank",
            "betweenness",
            "degree",
            "declared_criticality",
        }

    def test_an_empty_graph_has_no_critical_assets(self) -> None:
        assert critical_assets(Graph.from_subgraph(Subgraph())) == []


class TestRiskPropagation:
    """Spreading risk outward from failures."""

    def test_risk_decays_with_distance(self, chain: Graph) -> None:
        risk = risk_propagation(chain, failed_keys=["d"], decay=0.5)
        assert risk["d"] == 1.0
        assert risk["c"] == pytest.approx(0.5)
        assert risk["b"] == pytest.approx(0.25)

    def test_two_failures_take_the_higher_risk_not_the_sum(self) -> None:
        # Something already fully broken by one failure is not more
        # broken by a second.
        graph = Graph.from_subgraph(
            Subgraph(
                nodes=[node(k) for k in ("app", "db1", "db2")],
                relationships=[edge("app", "db1"), edge("app", "db2")],
            )
        )
        risk = risk_propagation(graph, failed_keys=["db1", "db2"], decay=0.6)
        assert risk["app"] == pytest.approx(0.6)

    def test_edge_weight_scales_propagation(self) -> None:
        graph = Graph.from_subgraph(
            Subgraph(
                nodes=[node("app"), node("db")],
                relationships=[edge("app", "db", weight=0.5)],
            )
        )
        risk = risk_propagation(graph, failed_keys=["db"], decay=1.0)
        assert risk["app"] == pytest.approx(0.5)

    def test_depth_bounds_the_spread(self, chain: Graph) -> None:
        risk = risk_propagation(chain, failed_keys=["d"], decay=1.0, max_depth=1)
        assert "c" in risk
        assert "a" not in risk

    def test_an_unknown_failed_node_propagates_nothing(self, chain: Graph) -> None:
        assert risk_propagation(chain, failed_keys=["ghost"]) == {}


class TestSizeCeiling:
    """The guard that keeps O(V*E) honest."""

    def test_a_graph_within_the_ceiling_passes(self, chain: Graph) -> None:
        require_size(chain, ceiling=10)

    def test_a_graph_over_the_ceiling_is_refused_with_its_size(self, chain: Graph) -> None:
        # Refused with the actual number, so a caller can narrow the
        # scope rather than guess.
        with pytest.raises(ValidationError, match="4 nodes"):
            require_size(chain, ceiling=2)


class TestDependencyScoring:
    """The traversal-side scoring in app/dependencies/engine.py."""

    def test_adjacency_reverses_for_an_inward_analysis(self) -> None:
        subgraph = Subgraph(nodes=[node("a"), node("b")], relationships=[edge("a", "b")])
        outward = build_adjacency(subgraph, direction=TraversalDirection.OUTGOING)
        inward = build_adjacency(subgraph, direction=TraversalDirection.INCOMING)
        assert outward["a"] == [("b", 1.0)]
        assert inward["b"] == [("a", 1.0)]

    def test_both_directions_index_each_edge_twice(self) -> None:
        subgraph = Subgraph(nodes=[node("a"), node("b")], relationships=[edge("a", "b")])
        adjacency = build_adjacency(subgraph, direction=TraversalDirection.BOTH)
        assert adjacency["a"] == [("b", 1.0)]
        assert adjacency["b"] == [("a", 1.0)]

    def test_scoring_decays_with_distance(self) -> None:
        subgraph = Subgraph(
            nodes=[node(k) for k in ("a", "b", "c")],
            relationships=[edge("a", "b"), edge("b", "c")],
        )
        affected = score_affected(
            root_key="a", subgraph=subgraph, direction=TraversalDirection.OUTGOING
        )
        by_key = {one.node.key: one for one in affected}
        assert by_key["b"].distance == 1
        assert by_key["c"].distance == 2
        assert by_key["b"].impact_score == pytest.approx(DISTANCE_DECAY)
        assert by_key["c"].impact_score == pytest.approx(DISTANCE_DECAY**2)

    def test_a_cycle_terminates(self) -> None:
        # Real estates contain A depends on B depends on A. Without a
        # visited set this runs to the depth ceiling.
        subgraph = Subgraph(
            nodes=[node("a"), node("b")],
            relationships=[edge("a", "b"), edge("b", "a")],
        )
        affected = score_affected(
            root_key="a", subgraph=subgraph, direction=TraversalDirection.OUTGOING
        )
        assert [one.node.key for one in affected] == ["b"]

    def test_multiple_routes_are_counted_but_not_re_scored(self) -> None:
        # A node reachable by four paths is not four times as broken.
        subgraph = Subgraph(
            nodes=[node(k) for k in ("root", "left", "right", "shared")],
            relationships=[
                edge("root", "left"),
                edge("root", "right"),
                edge("left", "shared"),
                edge("right", "shared"),
            ],
        )
        affected = score_affected(
            root_key="root", subgraph=subgraph, direction=TraversalDirection.OUTGOING
        )
        shared = next(one for one in affected if one.node.key == "shared")
        assert shared.paths == 2
        assert shared.impact_score == pytest.approx(DISTANCE_DECAY**2)

    def test_results_are_strongest_first(self) -> None:
        subgraph = Subgraph(
            nodes=[node(k) for k in ("a", "b", "c")],
            relationships=[edge("a", "b"), edge("b", "c")],
        )
        affected = score_affected(
            root_key="a", subgraph=subgraph, direction=TraversalDirection.OUTGOING
        )
        scores = [one.impact_score for one in affected]
        assert scores == sorted(scores, reverse=True)

    def test_risk_is_the_maximum_not_the_sum(self) -> None:
        # A sum grows with estate size, so a large healthy environment
        # would score worse than a small fragile one.
        result = AnalysisResult(
            root=node("root"),
            direction=TraversalDirection.INCOMING,
            affected=[
                AffectedNode(node=node("a"), distance=1, impact_score=0.6),
                AffectedNode(node=node("b"), distance=1, impact_score=0.3),
                AffectedNode(node=node("c"), distance=2, impact_score=0.2),
            ],
        )
        assert result.risk_score == 0.6

    def test_severity_bands_the_risk_score(self) -> None:
        for score, expected in ((0.9, "critical"), (0.6, "high"), (0.3, "medium"), (0.1, "low")):
            result = AnalysisResult(
                root=node("root"),
                direction=TraversalDirection.INCOMING,
                affected=[AffectedNode(node=node("a"), distance=1, impact_score=score)],
            )
            assert str(result.severity) == expected

    def test_nothing_affected_is_no_risk(self) -> None:
        result = AnalysisResult(root=node("root"), direction=TraversalDirection.INCOMING)
        assert result.risk_score == 0.0
        assert str(result.severity) == "low"

    def test_affected_are_counted_by_type(self) -> None:
        result = AnalysisResult(
            root=node("root"),
            direction=TraversalDirection.INCOMING,
            affected=[
                AffectedNode(node=node("a", "Application"), distance=1, impact_score=0.5),
                AffectedNode(node=node("b", "Application"), distance=1, impact_score=0.5),
                AffectedNode(node=node("c", "Database"), distance=2, impact_score=0.2),
            ],
        )
        assert result.by_type() == {"Application": 2, "Database": 1}

    def test_dependency_score_weighs_proximity_over_breadth(self) -> None:
        # Two immediate dependencies is more fragile than twenty at four
        # hops, and a plain count would rank them the other way round.
        close = AnalysisResult(
            root=node("root"),
            direction=TraversalDirection.OUTGOING,
            affected=[
                AffectedNode(node=node(f"n{i}"), distance=1, impact_score=0.6) for i in range(5)
            ],
        )
        far = AnalysisResult(
            root=node("root"),
            direction=TraversalDirection.OUTGOING,
            affected=[
                AffectedNode(node=node(f"n{i}"), distance=4, impact_score=0.1) for i in range(5)
            ],
        )
        assert dependency_score(close) > dependency_score(far)

    def test_dependency_score_of_nothing_is_zero(self) -> None:
        result = AnalysisResult(root=node("root"), direction=TraversalDirection.OUTGOING)
        assert dependency_score(result) == 0.0

    def test_an_analysis_serialises_completely(self) -> None:
        result = AnalysisResult(
            root=node("root"),
            direction=TraversalDirection.INCOMING,
            affected=[AffectedNode(node=node("a"), distance=1, impact_score=0.5)],
        )
        payload = result.as_dict()
        assert set(payload) == {
            "root",
            "direction",
            "depth",
            "affected",
            "affected_count",
            "affected_by_type",
            "relationships",
            "risk_score",
            "severity",
            "truncated",
        }
