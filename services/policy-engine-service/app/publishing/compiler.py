"""Compiling authored rules into the form evaluation reads.

Publishing is the moment an edit becomes policy. It does three things:
validates the whole rule tree, projects the authored
``policy_rules``/``policy_conditions`` rows into one
:attr:`~app.models.policy.Policy.compiled_rule` document, and records a
digest of the result.

**The digest is not a cache key.** It is the integrity check docs/050
asks for: a stored policy whose content no longer matches its recorded
checksum was changed by something that did not go through publishing,
and for the service that authorizes every protected operation on the
platform that is the one tampering signal worth having.

**Compilation is where a bad policy is caught.** Everything the rule
engine can refuse -- an unparseable pattern, an attribute path that is
not a path, a rule that nests too deep, an empty rule that would match
the whole estate -- is refused here, when a person is waiting for an
answer, rather than at 03:00 inside a decision nobody is watching.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import AttributeSource, LogicalOperator, RuleOperator
from app.models.rule import PolicyCondition, PolicyRule
from app.rules.engine import (
    Condition,
    Rule,
    count_conditions,
    rule_from_dict,
    validate_rule,
)


def build_tree(
    rules: list[PolicyRule], conditions: list[PolicyCondition], *, policy_slug: str
) -> Rule:
    """Assemble authored rows into one rule tree.

    Raises:
        ValidationError: If the rows do not form a single tree -- no
            root, several roots, or a cycle. Each is a corrupt policy
            rather than an unusual one, and evaluating any of them would
            mean silently choosing which fragment counts.
    """
    enabled_rules = [one for one in rules if one.is_enabled]
    if not enabled_rules:
        raise ValidationError(
            f"Policy {policy_slug!r} has no enabled rules, so it would never match. "
            "Add a rule before publishing."
        )

    by_parent: dict[UUID | None, list[PolicyRule]] = {}
    for row in sorted(enabled_rules, key=lambda one: (one.display_order, str(one.id))):
        by_parent.setdefault(row.parent_rule_id, []).append(row)

    conditions_by_rule: dict[UUID, list[PolicyCondition]] = {}
    for row in sorted(conditions, key=lambda one: (one.display_order, str(one.id))):
        if row.is_enabled:
            conditions_by_rule.setdefault(row.rule_id, []).append(row)

    roots = by_parent.get(None, [])
    if len(roots) != 1:
        raise ValidationError(
            f"Policy {policy_slug!r} must have exactly one root rule, found {len(roots)}. "
            "A policy with several roots has no defined way to combine them."
        )

    known = {one.id for one in enabled_rules}
    seen: set[UUID] = set()

    def _build(row: PolicyRule) -> Rule:
        if row.id in seen:
            raise ValidationError(
                f"Policy {policy_slug!r} has a cycle in its rule tree at {row.name!r}."
            )
        seen.add(row.id)
        return Rule(
            name=row.name,
            logical_operator=LogicalOperator(str(row.logical_operator)),
            conditions=[_condition(one) for one in conditions_by_rule.get(row.id, [])],
            children=[_build(child) for child in by_parent.get(row.id, []) if child.id in known],
            negate=row.negate,
            description=row.description or "",
        )

    return _build(roots[0])


def _condition(row: PolicyCondition) -> Condition:
    """Project one authored condition row.

    Raises:
        ValidationError: If the row names an operator or source that no
            longer exists -- which happens when a stored policy outlives
            an enum member, and must fail loudly rather than evaluate as
            something adjacent.
    """
    try:
        source = AttributeSource(str(row.attribute_source))
        operator = RuleOperator(str(row.operator))
    except ValueError as exc:
        raise ValidationError(
            f"Condition on {row.attribute_path!r} names something unknown: {exc}"
        ) from exc

    return Condition(
        source=source,
        path=row.attribute_path,
        operator=operator,
        value=(row.comparison_value or {}).get("value"),
        negate=row.negate,
        description=row.description or "",
    )


def canonical_json(payload: dict[str, Any]) -> str:
    """Render a rule document deterministically.

    Sorted keys and no incidental whitespace, so the digest depends on
    the policy's *content* rather than on dictionary ordering. Without
    it, republishing an unchanged policy would produce a different
    checksum and the integrity check would cry wolf on every deploy.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def checksum(compiled: dict[str, Any]) -> str:
    """The SHA-256 digest of a compiled rule document."""
    return hashlib.sha256(canonical_json(compiled).encode("utf-8")).hexdigest()


def compile_policy(
    rules: list[PolicyRule], conditions: list[PolicyCondition], *, policy_slug: str
) -> tuple[dict[str, Any], str, int]:
    """Validate and compile a policy's authored rules.

    Returns ``(compiled_rule, checksum, condition_count)``.

    Raises:
        ValidationError: If the tree is malformed or any rule or
            condition is unusable.
    """
    tree = build_tree(rules, conditions, policy_slug=policy_slug)
    validate_rule(tree)
    compiled = tree.as_dict()

    # Rebuilt and re-validated from its own serialised form before it is
    # stored. Compilation and loading are different code paths, and a
    # document that compiles but will not load is a policy that breaks
    # at the next restart rather than now -- which is exactly the class
    # of bug a round trip catches and nothing else does.
    validate_rule(rule_from_dict(compiled, name=policy_slug))

    return compiled, checksum(compiled), count_conditions(tree)


def verify_integrity(compiled: dict[str, Any], recorded: str | None) -> dict[str, Any]:
    """Check a stored policy against its recorded digest.

    A policy with no recorded digest is reported as unverifiable rather
    than valid: it predates integrity recording or was written by
    something that bypassed publishing, and calling that "valid" is the
    answer nobody wants from an integrity check.
    """
    if not recorded:
        return {
            "verified": False,
            "reason": "no checksum was recorded for this policy",
            "computed": checksum(compiled),
        }
    computed = checksum(compiled)
    return {
        "verified": computed == recorded,
        "recorded": recorded,
        "computed": computed,
        "reason": "" if computed == recorded else "the stored rule does not match its checksum",
    }


def next_version(current: str, *, breaking: bool = False, feature: bool = False) -> str:
    """The next semantic version after *current*.

    Raises:
        ValidationError: If the current version is not ``major.minor.patch``.
    """
    parts = current.split(".")
    expected_parts = 3
    if len(parts) != expected_parts or not all(one.isdigit() for one in parts):
        raise ValidationError(
            f"{current!r} is not a semantic version; expected 'major.minor.patch'."
        )
    major, minor, patch = (int(one) for one in parts)
    if breaking:
        return f"{major + 1}.0.0"
    if feature:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


__all__ = [
    "build_tree",
    "canonical_json",
    "checksum",
    "compile_policy",
    "next_version",
    "verify_integrity",
]
