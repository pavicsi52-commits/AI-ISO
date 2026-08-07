"""Tests for ``app.dependencies.engine``: ``creates_cycle`` and
``resolve_install_order`` over a plain ``dict[UUID, list[UUID]]`` edge
map (``plugin_id`` -> its own ``depends_on_plugin_id`` list).

No infrastructure needed -- these are pure functions over in-memory
graphs built with fresh ``uuid.uuid4()`` nodes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.dependencies.engine import CircularDependencyError, creates_cycle, resolve_install_order


def _node() -> UUID:
    return uuid4()


# ---- creates_cycle -------------------------------------------------------------


def test_no_cycle_when_new_dependency_is_unrelated() -> None:
    a, b, c = _node(), _node(), _node()
    # b depends on a, c depends on a -- no relationship to b at all yet.
    edges: dict[UUID, list[UUID]] = {b: [a], c: [a]}
    assert creates_cycle(edges, origin=b, new_dependency=c) is False


def test_self_dependency_is_always_a_cycle() -> None:
    a = _node()
    assert creates_cycle({}, origin=a, new_dependency=a) is True


def test_two_node_cycle_is_detected() -> None:
    a, b = _node(), _node()
    # b already depends on a. Adding "a depends on b" closes a 2-cycle.
    edges: dict[UUID, list[UUID]] = {b: [a]}
    assert creates_cycle(edges, origin=a, new_dependency=b) is True


def test_three_node_cycle_is_detected() -> None:
    a, b, c = _node(), _node(), _node()
    # b depends on a, c depends on b. Adding "a depends on c" closes a 3-cycle.
    edges: dict[UUID, list[UUID]] = {b: [a], c: [b]}
    assert creates_cycle(edges, origin=a, new_dependency=c) is True


def test_four_node_cycle_is_detected() -> None:
    a, b, c, d = _node(), _node(), _node(), _node()
    # b->a, c->b, d->c. Adding "a depends on d" closes a 4-cycle.
    edges: dict[UUID, list[UUID]] = {b: [a], c: [b], d: [c]}
    assert creates_cycle(edges, origin=a, new_dependency=d) is True


def test_disconnected_components_do_not_falsely_report_a_cycle() -> None:
    a, b, c, d = _node(), _node(), _node(), _node()
    # Two entirely separate chains: b->a, d->c.
    edges: dict[UUID, list[UUID]] = {b: [a], d: [c]}
    assert creates_cycle(edges, origin=b, new_dependency=d) is False
    assert creates_cycle(edges, origin=a, new_dependency=c) is False


def test_isolated_node_with_no_edges_at_all_is_not_a_cycle() -> None:
    isolated_a, isolated_b = _node(), _node()
    assert creates_cycle({}, origin=isolated_a, new_dependency=isolated_b) is False


def test_isolated_node_referenced_by_nothing_does_not_reach_unrelated_origin() -> None:
    a, b, isolated = _node(), _node(), _node()
    edges: dict[UUID, list[UUID]] = {b: [a]}
    assert creates_cycle(edges, origin=b, new_dependency=isolated) is False


def test_existing_edges_are_not_mutated() -> None:
    a, b = _node(), _node()
    edges: dict[UUID, list[UUID]] = {b: [a]}
    creates_cycle(edges, origin=a, new_dependency=b)
    assert edges == {b: [a]}


# ---- resolve_install_order -----------------------------------------------------


def test_empty_graph_returns_empty_order() -> None:
    assert resolve_install_order({}) == []


def test_isolated_node_appears_in_its_own_order() -> None:
    isolated = _node()
    order = resolve_install_order({isolated: []})
    assert order == [isolated]


def test_linear_chain_orders_dependencies_before_dependents() -> None:
    a, b, c, d = _node(), _node(), _node(), _node()
    # d depends on c, c depends on b, b depends on a.
    edges: dict[UUID, list[UUID]] = {d: [c], c: [b], b: [a]}
    order = resolve_install_order(edges)
    assert set(order) == {a, b, c, d}
    assert order.index(a) < order.index(b) < order.index(c) < order.index(d)


def test_diamond_shaped_graph_respects_every_dependency_edge() -> None:
    a, b, c, d = _node(), _node(), _node(), _node()
    # d depends on both b and c; b and c both depend on a.
    edges: dict[UUID, list[UUID]] = {d: [b, c], b: [a], c: [a]}
    order = resolve_install_order(edges)
    assert set(order) == {a, b, c, d}
    for node in edges:
        node_index = order.index(node)
        for dependency in edges[node]:
            assert order.index(dependency) < node_index


def test_disconnected_components_are_each_ordered_correctly() -> None:
    a, b, c, d = _node(), _node(), _node(), _node()
    edges: dict[UUID, list[UUID]] = {b: [a], d: [c]}
    order = resolve_install_order(edges)
    assert set(order) == {a, b, c, d}
    assert order.index(a) < order.index(b)
    assert order.index(c) < order.index(d)


def test_every_node_appears_exactly_once() -> None:
    a, b, c = _node(), _node(), _node()
    # c depends on both a and b; a and b are otherwise unrelated.
    edges: dict[UUID, list[UUID]] = {c: [a, b], a: [], b: []}
    order = resolve_install_order(edges)
    assert sorted(order) == sorted({a, b, c})
    assert len(order) == 3


def test_two_node_cycle_raises_circular_dependency_error() -> None:
    a, b = _node(), _node()
    edges: dict[UUID, list[UUID]] = {a: [b], b: [a]}
    with pytest.raises(CircularDependencyError):
        resolve_install_order(edges)


def test_three_node_cycle_raises_circular_dependency_error() -> None:
    a, b, c = _node(), _node(), _node()
    edges: dict[UUID, list[UUID]] = {a: [b], b: [c], c: [a]}
    with pytest.raises(CircularDependencyError):
        resolve_install_order(edges)


def test_self_dependency_raises_circular_dependency_error() -> None:
    a = _node()
    edges: dict[UUID, list[UUID]] = {a: [a]}
    with pytest.raises(CircularDependencyError):
        resolve_install_order(edges)


def test_cycle_in_one_component_does_not_prevent_detection_via_the_other() -> None:
    a, b, c, d = _node(), _node(), _node(), _node()
    # c->d is a normal edge; a<->b is a cycle. Order of dict entries
    # (c/d visited first) must not hide the later a/b cycle.
    edges: dict[UUID, list[UUID]] = {c: [d], d: [], a: [b], b: [a]}
    with pytest.raises(CircularDependencyError):
        resolve_install_order(edges)
