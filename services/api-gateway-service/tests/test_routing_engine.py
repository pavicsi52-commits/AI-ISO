"""Pure tests for app/routing/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest

from app.models.enums import RouteMatchKind
from app.routing.engine import (
    RouteCandidate,
    _weighted_choice,
    headers_match,
    host_matches,
    path_matches,
    resolve_target_path,
    select_candidates,
    select_route,
)

pytestmark = pytest.mark.asyncio


def _route(
    *,
    id: str = "r1",
    service_id: str = "s1",
    match_kind: RouteMatchKind = RouteMatchKind.PATH,
    path_pattern: str = "/orders",
    host_pattern: str | None = None,
    methods: tuple[str, ...] = (),
    header_match: dict[str, str] | None = None,
    weight: int = 100,
    priority: int = 100,
    strip_prefix: bool = False,
    rewrite_path: str | None = None,
    is_fallback: bool = False,
    enabled: bool = True,
) -> RouteCandidate:
    return RouteCandidate(
        id=id,
        service_id=service_id,
        match_kind=match_kind,
        path_pattern=path_pattern,
        host_pattern=host_pattern,
        methods=methods,
        header_match=header_match or {},
        weight=weight,
        priority=priority,
        strip_prefix=strip_prefix,
        rewrite_path=rewrite_path,
        is_fallback=is_fallback,
        enabled=enabled,
    )


class TestPathMatches:
    async def test_static_exact_match(self) -> None:
        assert path_matches("/orders", "/orders") is True

    async def test_static_mismatch(self) -> None:
        assert path_matches("/orders", "/users") is False

    async def test_single_wildcard_matches_exactly_one_segment(self) -> None:
        assert path_matches("/orders/*", "/orders/123") is True

    async def test_single_wildcard_does_not_match_extra_trailing_segments(self) -> None:
        assert path_matches("/orders/*", "/orders/123/extra") is False

    async def test_double_wildcard_matches_zero_segments(self) -> None:
        assert path_matches("/orders/**", "/orders") is True

    async def test_double_wildcard_matches_many_segments(self) -> None:
        assert path_matches("/orders/**", "/orders/123/456") is True

    async def test_double_wildcard_matches_embedded_in_the_middle_of_a_pattern(self) -> None:
        assert path_matches("/a/**/b", "/a/x/y/b") is True

    async def test_double_wildcard_embedded_excludes_a_path_missing_the_suffix(self) -> None:
        assert path_matches("/a/**/b", "/a/x/y/c") is False

    async def test_empty_pattern_matches_only_the_empty_path(self) -> None:
        assert path_matches("", "") is True
        assert path_matches("", "/foo") is False

    async def test_pattern_longer_than_path_does_not_match(self) -> None:
        assert path_matches("/a/b", "/a") is False

    async def test_path_longer_than_pattern_does_not_match(self) -> None:
        assert path_matches("/a", "/a/b") is False


class TestHostMatches:
    async def test_none_pattern_matches_any_host(self) -> None:
        assert host_matches(None, "example.com") is True

    async def test_none_pattern_matches_a_none_host(self) -> None:
        assert host_matches(None, None) is True

    async def test_a_pattern_never_matches_a_none_host(self) -> None:
        assert host_matches("example.com", None) is False

    async def test_exact_match(self) -> None:
        assert host_matches("example.com", "example.com") is True

    async def test_exact_mismatch(self) -> None:
        assert host_matches("example.com", "other.com") is False

    async def test_wildcard_matches_a_subdomain(self) -> None:
        assert host_matches("*.example.com", "api.example.com") is True

    async def test_wildcard_excludes_the_bare_apex_domain(self) -> None:
        assert host_matches("*.example.com", "example.com") is False

    async def test_wildcard_does_not_match_an_unrelated_domain(self) -> None:
        assert host_matches("*.example.com", "example.org") is False


class TestHeadersMatch:
    async def test_no_required_headers_always_matches(self) -> None:
        assert headers_match({}, {}) is True
        assert headers_match({}, {"X-Foo": "1"}) is True

    async def test_required_header_key_comparison_is_case_insensitive(self) -> None:
        assert headers_match({"X-Foo": "bar"}, {"x-foo": "bar"}) is True

    async def test_missing_header_fails(self) -> None:
        assert headers_match({"X-Foo": "bar"}, {}) is False

    async def test_value_mismatch_fails(self) -> None:
        assert headers_match({"X-Foo": "bar"}, {"X-Foo": "baz"}) is False

    async def test_all_of_multiple_required_headers_must_match(self) -> None:
        required = {"X-Foo": "1", "X-Bar": "2"}
        assert headers_match(required, {"X-Foo": "1", "X-Bar": "2"}) is True

    async def test_one_mismatch_among_multiple_required_headers_fails(self) -> None:
        required = {"X-Foo": "1", "X-Bar": "2"}
        assert headers_match(required, {"X-Foo": "1", "X-Bar": "wrong"}) is False


class TestSelectCandidates:
    async def test_disabled_routes_are_excluded(self) -> None:
        routes = [_route(enabled=False)]
        assert select_candidates(routes, method="get", path="/orders") == []

    async def test_fallback_routes_are_excluded_even_if_otherwise_matching(self) -> None:
        routes = [_route(is_fallback=True)]
        assert select_candidates(routes, method="get", path="/orders") == []

    async def test_empty_methods_tuple_matches_any_method(self) -> None:
        route = _route(methods=())
        assert select_candidates([route], method="delete", path="/orders") == [route]

    async def test_specific_methods_exclude_a_mismatched_method(self) -> None:
        route = _route(methods=("get", "post"))
        assert select_candidates([route], method="delete", path="/orders") == []

    async def test_method_matching_is_case_insensitive(self) -> None:
        route = _route(methods=("get",))
        assert select_candidates([route], method="GET", path="/orders") == [route]

    async def test_path_mismatch_excludes_a_route(self) -> None:
        route = _route(path_pattern="/orders")
        assert select_candidates([route], method="get", path="/users") == []

    async def test_host_mismatch_excludes_a_route_when_host_is_given(self) -> None:
        route = _route(host_pattern="api.example.com")
        assert select_candidates([route], method="get", path="/orders", host="other.com") == []

    async def test_headers_mismatch_excludes_a_route_when_headers_are_given(self) -> None:
        route = _route(header_match={"X-Foo": "1"})
        assert select_candidates([route], method="get", path="/orders", headers={}) == []

    async def test_matching_candidates_are_sorted_by_priority_ascending(self) -> None:
        low = _route(id="low", priority=50)
        mid = _route(id="mid", priority=10)
        high = _route(id="high", priority=30)
        result = select_candidates([low, mid, high], method="get", path="/orders")
        assert [route.id for route in result] == ["mid", "high", "low"]


class TestSelectRoute:
    async def test_returns_none_when_nothing_matches_and_there_is_no_fallback(self) -> None:
        routes = [_route(path_pattern="/users")]
        assert select_route(routes, method="get", path="/orders") is None

    async def test_returns_the_fallback_when_nothing_else_matches(self) -> None:
        fallback = _route(id="fb", is_fallback=True, enabled=True)
        other = _route(id="other", path_pattern="/users")
        result = select_route([other, fallback], method="get", path="/orders")
        assert result is fallback

    async def test_ignores_a_disabled_fallback_when_nothing_matches(self) -> None:
        fallback = _route(id="fb", is_fallback=True, enabled=False)
        assert select_route([fallback], method="get", path="/orders") is None

    async def test_returns_the_only_matching_candidate(self) -> None:
        route = _route(id="only")
        assert select_route([route], method="get", path="/orders") is route

    async def test_prefers_the_lower_priority_number(self) -> None:
        winner = _route(id="winner", priority=1)
        loser = _route(id="loser", priority=99)
        result = select_route([loser, winner], method="get", path="/orders")
        assert result is winner

    async def test_multiple_same_priority_non_weighted_routes_return_the_first_in_original_order(
        self,
    ) -> None:
        first = _route(id="first", priority=5)
        second = _route(id="second", priority=5)
        result = select_route([first, second], method="get", path="/orders")
        assert result is first

    async def test_a_single_weighted_route_beside_a_non_weighted_one_skips_random_choice(
        self,
    ) -> None:
        weighted = _route(id="weighted", priority=5, match_kind=RouteMatchKind.WEIGHTED, weight=1)
        plain = _route(id="plain", priority=5, match_kind=RouteMatchKind.STATIC)
        result = select_route([weighted, plain], method="get", path="/orders")
        assert result is weighted  # first in the (stable-sorted) top band, no randomness involved

    async def test_multiple_weighted_routes_at_the_same_priority_use_weighted_random_choice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        route_a = _route(id="a", priority=1, match_kind=RouteMatchKind.WEIGHTED, weight=30)
        route_b = _route(id="b", priority=1, match_kind=RouteMatchKind.WEIGHTED, weight=70)

        monkeypatch.setattr("app.routing.engine.random.uniform", lambda _a, _b: 10.0)
        low_pick = select_route([route_a, route_b], method="get", path="/orders")
        assert low_pick is route_a  # running total after `a` (30) already covers pick=10

        monkeypatch.setattr("app.routing.engine.random.uniform", lambda _a, _b: 50.0)
        high_pick = select_route([route_a, route_b], method="get", path="/orders")
        assert high_pick is route_b  # running total after `a` (30) doesn't cover pick=50


class TestWeightedChoice:
    async def test_a_pick_that_would_exceed_every_running_total_falls_back_to_the_last_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Defensive-only branch: `pick` is drawn from [0, total_weight], so it should never
        # exceed the final running total in practice, but float summation makes it possible.
        routes = [_route(id="a", weight=10), _route(id="b", weight=20)]
        monkeypatch.setattr("app.routing.engine.random.uniform", lambda _a, _b: 999.0)
        assert _weighted_choice(routes) is routes[-1]

    async def test_zero_total_weight_still_returns_a_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        routes = [_route(id="a", weight=0), _route(id="b", weight=0)]
        monkeypatch.setattr("app.routing.engine.random.uniform", lambda _a, _b: 0.0)
        assert _weighted_choice(routes) is routes[0]


class TestResolveTargetPath:
    async def test_no_stripping_no_rewrite_returns_the_request_path_unchanged(self) -> None:
        route = _route(strip_prefix=False, rewrite_path=None)
        assert resolve_target_path(route, "/orders/123") == "/orders/123"

    async def test_strip_prefix_removes_the_matched_prefix(self) -> None:
        route = _route(path_pattern="/api/orders/*", strip_prefix=True)
        assert resolve_target_path(route, "/api/orders/123") == "/123"

    async def test_strip_prefix_leaving_nothing_yields_a_bare_slash(self) -> None:
        route = _route(path_pattern="/api/orders/*", strip_prefix=True)
        assert resolve_target_path(route, "/api/orders") == "/"

    async def test_strip_prefix_is_a_no_op_when_the_path_does_not_start_with_the_prefix(
        self,
    ) -> None:
        route = _route(path_pattern="/api/orders/*", strip_prefix=True)
        assert resolve_target_path(route, "/other/path") == "/other/path"

    async def test_strip_prefix_never_strips_when_the_pattern_has_no_static_prefix(self) -> None:
        route = _route(path_pattern="*", strip_prefix=True)
        assert resolve_target_path(route, "/orders/123") == "/orders/123"

    async def test_rewrite_path_overrides_the_original_path(self) -> None:
        route = _route(strip_prefix=False, rewrite_path="/v2/orders")
        assert resolve_target_path(route, "/orders/123") == "/v2/orders"

    async def test_rewrite_path_overrides_even_the_stripped_result(self) -> None:
        route = _route(path_pattern="/api/orders/*", strip_prefix=True, rewrite_path="/v2")
        assert resolve_target_path(route, "/api/orders/123") == "/v2"
