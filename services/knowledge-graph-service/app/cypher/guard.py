"""Read-only enforcement for caller-authored Cypher ("SECURITY").

``POST /graph/cypher`` accepts Cypher a user wrote. That is a genuinely
useful capability for an operator chasing a relationship this service's
built-in queries do not express -- and it is also the single most
dangerous endpoint in the platform, because Cypher can delete the
entire graph in eight characters.

Three layers, in order:

1. **Neo4j enforces it.** The statement runs in an explicitly
   *read* transaction. A write clause fails at the database, not on
   trust. This is the layer that actually holds.
2. **This module refuses it first**, so the caller gets a clear message
   naming the clause rather than a driver error, and so a refusal is
   audited as ``DENIED`` before anything reaches Neo4j.
3. **Every value must be a bound parameter.** A statement containing a
   string or numeric literal where a parameter belongs is refused, which
   is what stops "read-only" from meaning "read anything, including
   other tenants".

**On the parsing.** This is a lexical check, not a Cypher parser.
Comments and string contents are stripped first so a keyword inside a
quoted value is not mistaken for a clause, and the match is on whole
words. It is deliberately conservative: a statement it cannot confidently
classify is refused. Being wrong in the permissive direction here means
someone deletes production; being wrong in the strict direction means an
operator asks for a built-in query. Those costs are not comparable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared_core.exceptions.validation import ValidationError

WRITE_CLAUSES: frozenset[str] = frozenset(
    {
        "CREATE",
        "MERGE",
        "DELETE",
        "DETACH",
        "SET",
        "REMOVE",
        "DROP",
        "FOREACH",
        "LOAD",
    }
)
"""Clauses that can change the graph or the schema.

``FOREACH`` is included because its body is the one place a write can
hide inside what otherwise reads as a projection. ``LOAD`` covers
``LOAD CSV``, which reaches the filesystem and the network.
"""

FORBIDDEN_PROCEDURES: frozenset[str] = frozenset(
    {
        "apoc.create",
        "apoc.merge",
        "apoc.refactor",
        "apoc.periodic",
        "apoc.load",
        "apoc.export",
        "apoc.import",
        "apoc.cypher.dorunfirstcolumn",
        "apoc.cypher.run",
        "apoc.cypher.doit",
        "apoc.trigger",
        "apoc.util.sleep",
        "dbms.security",
        "dbms.killquery",
        "dbms.setconfigvalue",
        "db.createlabel",
        "db.index.fulltext.drop",
    }
)
"""Procedure namespaces that write, execute arbitrary Cypher, or touch
the host.

Checked by prefix, so ``apoc.create.node`` is caught by ``apoc.create``.
``apoc.cypher.run`` matters most: it executes a Cypher string built at
runtime, which would let a read-only statement smuggle a write past
every check above.
"""

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_PARAMETER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_NUMERIC_LITERAL = re.compile(r"(?<![\w.$])\d+(?:\.\d+)?(?![\w.])")
_VARIABLE_LENGTH = re.compile(r"\[[^\]]*\*[^\]]*\]")

_ALLOWED_BARE_NUMBERS: frozenset[str] = frozenset()
"""Numeric literals a read-only statement may contain: none.

A ``LIMIT 100`` looks harmless, but allowing bare numbers means allowing
``SKIP 999999`` and every other unparameterised value. The endpoint
applies its own limit, so the caller never needs one.
"""

_VARIABLE_LENGTH_REASON = (
    "Variable-length patterns such as [*1..3] are not permitted in custom "
    "Cypher. Cypher cannot bind a range as a parameter, so the depth would "
    "be unchecked -- and an unbounded traversal on a large estate is an "
    "outage. Use /graph/topology, /graph/dependencies, /graph/impact, or "
    "/graph/blast-radius, which take a depth and bound it."
)
"""Why a variable-length range is refused outright.

Found by a test: the numeric-literal check does **not** catch the bounds
in ``[*1..3]``, because ``1`` is followed by a dot and ``3`` is preceded
by one, so both fail the regex word-boundary guards. A read-only
statement could therefore request ``[*1..50]`` and pin the database.

Refused rather than bounded, which is the same stance the rest of this
module takes: depth is the one value Cypher cannot parameterise, so a
caller-authored statement has no safe way to express it. The built-in
traversal endpoints validate depth through
:func:`app.cypher.builder.validate_depth` and are the supported path.
"""


@dataclass(frozen=True, slots=True)
class GuardResult:
    """The outcome of inspecting one statement."""

    allowed: bool
    reason: str | None = None
    parameters_used: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        """Truthy when the statement may run."""
        return self.allowed


def strip_noise(cypher: str) -> str:
    """Remove comments and string contents, keeping the structure.

    String *contents* are blanked rather than the quotes removed, so a
    statement is still recognisably shaped afterwards and a keyword
    inside a quoted value cannot be mistaken for a clause. This is what
    stops ``RETURN 'please DELETE this'`` from being refused, and stops
    ``MATCH (n) /* DELETE */ RETURN n`` from hiding one.
    """
    without_comments = _COMMENT.sub(" ", cypher)
    return _STRING.sub("''", without_comments)


def inspect(cypher: str) -> GuardResult:
    """Classify one statement without raising.

    Returns a :class:`GuardResult` so a caller can audit a refusal
    before deciding what to do about it.
    """
    if not cypher or not cypher.strip():
        return GuardResult(allowed=False, reason="The Cypher statement is empty.")

    cleaned = strip_noise(cypher)
    words = {word.upper() for word in _WORD.findall(cleaned)}

    offending = sorted(WRITE_CLAUSES & words)
    if offending:
        return GuardResult(
            allowed=False,
            reason=(
                f"This endpoint runs read-only Cypher; {', '.join(offending)} "
                "would change the graph. Use the node and relationship "
                "endpoints for writes."
            ),
        )

    lowered = cleaned.lower()
    for procedure in sorted(FORBIDDEN_PROCEDURES):
        if procedure in lowered:
            return GuardResult(
                allowed=False,
                reason=(
                    f"Procedure namespace {procedure!r} is not permitted: it can "
                    "write, execute generated Cypher, or reach outside the database."
                ),
            )

    # Checked before the literal scan, because that scan cannot see the
    # bounds inside [*1..3] -- see _VARIABLE_LENGTH_REASON.
    if _VARIABLE_LENGTH.search(cleaned):
        return GuardResult(allowed=False, reason=_VARIABLE_LENGTH_REASON)

    literals = _NUMERIC_LITERAL.findall(cleaned)
    unexpected = [one for one in literals if one not in _ALLOWED_BARE_NUMBERS]
    if unexpected:
        return GuardResult(
            allowed=False,
            reason=(
                f"Every value must be a bound parameter; found literal "
                f"{unexpected[0]!r}. Write $name and supply it in parameters."
            ),
        )

    return GuardResult(allowed=True, parameters_used=frozenset(_PARAMETER.findall(cleaned)))


def require_read_only(cypher: str) -> frozenset[str]:
    """Refuse anything that is not a safe read-only statement.

    Returns the parameter names the statement binds, so a caller can
    check every one was supplied.

    Raises:
        ValidationError: With the specific reason, so the caller learns
            what to change rather than being told "invalid".
    """
    result = inspect(cypher)
    if not result.allowed:
        raise ValidationError(result.reason or "That Cypher statement is not permitted.")
    return result.parameters_used


def require_bound_parameters(cypher: str, parameters: dict[str, object]) -> None:
    """Refuse a statement whose parameters were not all supplied.

    Neo4j would otherwise treat a missing parameter as ``null``, and a
    filter comparing against ``null`` silently matches nothing -- an
    empty result that looks like a real answer.

    Raises:
        ValidationError: If any referenced parameter is missing.
    """
    referenced = inspect(cypher).parameters_used
    missing = sorted(referenced - set(parameters))
    if missing:
        raise ValidationError(
            f"These parameters are referenced but not supplied: {', '.join(missing)}. "
            "An unbound parameter is null in Cypher, which matches nothing."
        )


__all__ = [
    "FORBIDDEN_PROCEDURES",
    "WRITE_CLAUSES",
    "GuardResult",
    "inspect",
    "require_bound_parameters",
    "require_read_only",
    "strip_noise",
]
