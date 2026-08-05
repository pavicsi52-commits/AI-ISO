"""Pure routing decisions.

Nothing in `shared_core` implements route matching (confirmed during
this prompt's own research phase: no `load_balanc`/routing primitive
exists anywhere in the framework) -- this is a genuine gap, built new,
per this prompt's own "use every previously implemented platform
framework" instruction applying only where a framework already exists.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.models.enums import RouteMatchKind


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """The fields of one stored :class:`~app.models.route.ApiRoute` row a routing
    decision actually needs, decoupled from the ORM row so this module
    stays a pure function of its inputs."""

    id: str
    service_id: str
    match_kind: RouteMatchKind
    path_pattern: str
    host_pattern: str | None
    methods: tuple[str, ...]
    header_match: dict[str, str]
    weight: int
    priority: int
    strip_prefix: bool
    rewrite_path: str | None
    is_fallback: bool
    enabled: bool


def path_matches(pattern: str, path: str) -> bool:
    """Whether *path* matches *pattern*.

    ``*`` matches exactly one path segment; ``**`` matches any number of
    segments, including zero -- the same two-token vocabulary every
    reverse proxy's own route-matching language already uses (nginx,
    Envoy, Kubernetes Ingress).
    """
    pattern_segments = pattern.strip("/").split("/") if pattern.strip("/") else []
    path_segments = path.strip("/").split("/") if path.strip("/") else []
    return _match_segments(pattern_segments, path_segments)


def _match_segments(pattern_segments: list[str], path_segments: list[str]) -> bool:
    if not pattern_segments:
        return not path_segments
    head, *rest = pattern_segments
    if head == "**":
        if not rest:
            return True
        return any(_match_segments(rest, path_segments[i:]) for i in range(len(path_segments) + 1))
    if not path_segments:
        return False
    if head != "*" and head != path_segments[0]:
        return False
    return _match_segments(rest, path_segments[1:])


def host_matches(pattern: str | None, host: str | None) -> bool:
    """Whether *host* matches *pattern*.

    ``None`` always matches (no host restriction). A leading ``*.``
    matches any single subdomain prefix, never the bare apex domain.
    """
    if pattern is None:
        return True
    if host is None:
        return False
    if pattern.startswith("*."):
        suffix = pattern[1:]
        return host.endswith(suffix) and host != suffix.lstrip(".")
    return host == pattern


def headers_match(required: dict[str, str], actual: dict[str, str]) -> bool:
    """Whether every required header/value pair is present in *actual* (case-insensitive keys)."""
    if not required:
        return True
    lowered = {key.lower(): value for key, value in actual.items()}
    return all(lowered.get(key.lower()) == value for key, value in required.items())


def select_candidates(
    routes: list[RouteCandidate],
    *,
    method: str,
    path: str,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> list[RouteCandidate]:
    """Every enabled, non-fallback route matching this request, ordered by priority."""
    headers = headers or {}
    matches = [
        route
        for route in routes
        if route.enabled
        and not route.is_fallback
        and (not route.methods or method.lower() in route.methods)
        and path_matches(route.path_pattern, path)
        and host_matches(route.host_pattern, host)
        and headers_match(route.header_match, headers)
    ]
    return sorted(matches, key=lambda route: route.priority)


def select_route(
    routes: list[RouteCandidate],
    *,
    method: str,
    path: str,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> RouteCandidate | None:
    """Resolve the one route that should handle this request, or ``None``.

    Every matching, enabled, non-fallback route is ranked by
    ``priority`` (lower first); when the best-ranked priority band has
    more than one ``WEIGHTED`` route, one is chosen by weighted-random
    selection *within that band only*, so a route's weight only ever
    competes against the routes it was actually configured to share
    traffic with. If nothing matches, the single enabled route with
    ``is_fallback=True`` (if any) is returned ("Fallback Routing").
    """
    candidates = select_candidates(routes, method=method, path=path, host=host, headers=headers)
    if candidates:
        best_priority = candidates[0].priority
        top_band = [route for route in candidates if route.priority == best_priority]
        weighted = [route for route in top_band if route.match_kind == RouteMatchKind.WEIGHTED]
        if len(weighted) > 1:
            return _weighted_choice(weighted)
        return top_band[0]
    fallbacks = [route for route in routes if route.enabled and route.is_fallback]
    return fallbacks[0] if fallbacks else None


def _weighted_choice(routes: list[RouteCandidate]) -> RouteCandidate:
    total_weight = sum(route.weight for route in routes) or 1
    pick = random.uniform(0, total_weight)
    running_total = 0.0
    for route in routes:
        running_total += route.weight
        if pick <= running_total:
            return route
    return routes[-1]


def resolve_target_path(route: RouteCandidate, request_path: str) -> str:
    """The path forwarded upstream, after optional prefix-stripping and rewriting."""
    path = request_path
    if route.strip_prefix:
        prefix = route.path_pattern.split("*")[0].rstrip("/")
        if prefix and path.startswith(prefix):
            path = path[len(prefix) :] or "/"
    if route.rewrite_path is not None:
        path = route.rewrite_path
    return path


__all__ = [
    "RouteCandidate",
    "headers_match",
    "host_matches",
    "path_matches",
    "resolve_target_path",
    "select_candidates",
    "select_route",
]
