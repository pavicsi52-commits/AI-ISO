"""Safe Cypher construction ("SECURITY": parameterized queries only).

This module is the whole injection defence, and it exists because
Cypher has three things that **cannot** be bound parameters:

1. **Node labels** -- ``MATCH (n:$label)`` is not valid Cypher.
2. **Relationship types** -- ``-[:$type]->`` is not valid either.
3. **Variable-length ranges** -- ``*1..$depth`` is not valid.

Everything else in every query this service builds is a real bound
parameter. Those three are handled by *validation against a closed
vocabulary* before any string formatting happens: labels and
relationship types must be members of :class:`~app.models.enums.NodeType`
and :class:`~app.models.enums.RelationshipType`, and a depth must be an
integer inside a configured ceiling.

That is the entire rule, and it is why every function below that
formats something into query text takes its input through a
``validate_*`` call first. A caller who reaches for an f-string
directly has bypassed the only thing standing between a user-authored
widget definition and ``DETACH DELETE``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from shared_core.exceptions.validation import ValidationError

from app.models.enums import NodeType, RelationshipType, TraversalDirection

MAX_DEPTH_CEILING = 15
"""Hard upper bound on traversal depth, whatever configuration says.

Traversal cost grows exponentially with depth. A configured ceiling can
be lowered but never raised past this.
"""

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""What a safe Cypher identifier looks like.

Used for property names, which -- like labels -- cannot be bound. The
pattern deliberately excludes backticks, whitespace, dots, and
everything else that could close an identifier and start a clause.
"""

_NODE_LABELS: frozenset[str] = frozenset(str(member) for member in NodeType)
_RELATIONSHIP_TYPES: frozenset[str] = frozenset(str(member) for member in RelationshipType)

_DIRECTION_PATTERNS: dict[TraversalDirection, tuple[str, str]] = {
    TraversalDirection.OUTGOING: ("-", "->"),
    TraversalDirection.INCOMING: ("<-", "-"),
    TraversalDirection.BOTH: ("-", "-"),
}
"""Arrow pair per direction.

A table rather than branches, because getting a direction backwards
answers "who breaks if I go down?" with "what do I need?" -- confidently,
and wrongly, at the exact moment an operator is relying on it.
"""


def validate_label(label: str | NodeType) -> str:
    """Return *label* if it is a known node label.

    Raises:
        ValidationError: If it is not. A label is part of the query
            text, so an unknown one is refused rather than escaped --
            there is no escaping that makes an arbitrary label safe.
    """
    text = str(label)
    if text not in _NODE_LABELS:
        raise ValidationError(
            f"Unknown node label {text!r}. Use one of the supported node types, "
            f"or {NodeType.CUSTOM_NODE} for an installation-specific kind."
        )
    return text


def validate_relationship_type(relationship_type: str | RelationshipType) -> str:
    """Return *relationship_type* if it is a known type.

    Raises:
        ValidationError: If it is not, for the same reason as
            :func:`validate_label`.
    """
    text = str(relationship_type)
    if text not in _RELATIONSHIP_TYPES:
        raise ValidationError(
            f"Unknown relationship type {text!r}. Use one of the supported types, "
            f"or {RelationshipType.CUSTOM_RELATIONSHIP} for an installation-specific one."
        )
    return text


def validate_relationship_types(
    types: Iterable[str | RelationshipType] | None,
) -> list[str]:
    """Validate a set of relationship types, preserving order.

    An empty or ``None`` input yields an empty list, which callers
    render as "any relationship" -- an unfiltered pattern, not a
    pattern built from unvalidated input.
    """
    return [validate_relationship_type(one) for one in (types or [])]


def validate_property_name(name: str) -> str:
    """Return *name* if it is a safe property identifier.

    Raises:
        ValidationError: If it is not. Property names appear in query
            text for ordering and filtering, so the same rule applies as
            for labels.
    """
    if not _IDENTIFIER.match(name):
        raise ValidationError(
            f"Property name {name!r} is not a valid identifier. Use letters, "
            "digits, and underscores, starting with a letter or underscore."
        )
    return name


def validate_depth(depth: int, *, ceiling: int) -> int:
    """Validate a traversal depth before it reaches a Cypher range literal.

    Raises:
        ValidationError: If the depth is not a positive integer within
            the configured ceiling. This is one of only three values
            this service ever formats into query text, and this check is
            what makes that safe.
    """
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise ValidationError(f"Traversal depth must be an integer, got {depth!r}.")
    limit = min(ceiling, MAX_DEPTH_CEILING)
    if depth < 1 or depth > limit:
        raise ValidationError(f"Traversal depth must be between 1 and {limit}, got {depth}.")
    return depth


def validate_limit(limit: int, *, ceiling: int) -> int:
    """Validate a result limit.

    Raises:
        ValidationError: If it is not a positive integer within the
            ceiling.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValidationError(f"Limit must be an integer, got {limit!r}.")
    if limit < 1 or limit > ceiling:
        raise ValidationError(f"Limit must be between 1 and {ceiling}, got {limit}.")
    return limit


def label_clause(labels: Sequence[str | NodeType] | None) -> str:
    """Render a validated label filter, e.g. ``:Application|Service``.

    Returns an empty string for no labels, which matches any node.
    """
    if not labels:
        return ""
    validated = [validate_label(one) for one in labels]
    return ":" + "|".join(validated)


def relationship_clause(
    types: Sequence[str | RelationshipType] | None,
    *,
    variable: str = "r",
    depth: int | None = None,
    ceiling: int = MAX_DEPTH_CEILING,
) -> str:
    """Render a validated relationship pattern body.

    With *depth*, produces a variable-length pattern such as
    ``r:DEPENDS_ON|USES*1..3``. The depth is validated first; it is the
    only interpolated number.
    """
    validated = validate_relationship_types(types)
    body = variable
    if validated:
        body += ":" + "|".join(validated)
    if depth is not None:
        body += f"*1..{validate_depth(depth, ceiling=ceiling)}"
    return body


def traversal_pattern(
    *,
    direction: TraversalDirection,
    types: Sequence[str | RelationshipType] | None = None,
    depth: int | None = None,
    ceiling: int = MAX_DEPTH_CEILING,
    variable: str = "r",
) -> str:
    """Render a complete relationship pattern including its arrows.

    Raises:
        ValidationError: If the direction, types, or depth are invalid.
    """
    arrows = _DIRECTION_PATTERNS.get(direction)
    if arrows is None:
        supported = ", ".join(sorted(str(one) for one in _DIRECTION_PATTERNS))
        raise ValidationError(
            f"Unsupported traversal direction {str(direction)!r}. Supported: {supported}."
        )
    left, right = arrows
    body = relationship_clause(types, variable=variable, depth=depth, ceiling=ceiling)
    return f"{left}[{body}]{right}"


def node_match(
    *,
    variable: str = "n",
    labels: Sequence[str | NodeType] | None = None,
    key_parameter: str | None = None,
) -> str:
    """Render a node pattern scoped to one organization.

    Every node this service writes carries ``organization_id``, and
    every read pattern filters on it. Tenant isolation is not a
    convention here -- it is in the pattern itself, bound as a
    parameter, so a query that forgets it does not compile into
    something that reads another tenant graph.
    """
    scope = "organization_id: $organization_id"
    if key_parameter is not None:
        scope = f"key: ${key_parameter}, " + scope
    return f"({variable}{label_clause(labels)} {{{scope}}})"


def order_clause(variable: str, property_name: str | None, *, descending: bool = False) -> str:
    """Render a validated ``ORDER BY`` clause, or an empty string."""
    if not property_name:
        return ""
    safe = validate_property_name(property_name)
    return f" ORDER BY {variable}.{safe} {'DESC' if descending else 'ASC'}"


__all__ = [
    "MAX_DEPTH_CEILING",
    "label_clause",
    "node_match",
    "order_clause",
    "relationship_clause",
    "traversal_pattern",
    "validate_depth",
    "validate_label",
    "validate_limit",
    "validate_property_name",
    "validate_relationship_type",
    "validate_relationship_types",
]
