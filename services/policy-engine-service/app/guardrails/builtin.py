"""The baseline guardrails a deployment starts with.

docs/050 asks for "Security Guardrails" and "Compliance Policies". These
are the platform's own, seeded per organization and marked
``is_system`` so they cannot be deleted -- only superseded by a
higher-precedence policy somebody deliberately wrote.

**They are deliberately few.** A long list of shipped policies is a list
somebody will disable wholesale the first time one gets in the way, and
the whole set goes with it. Each of these exists because its absence is
a specific, nameable incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import (
    ActionType,
    AttributeSource,
    ComplianceStandard,
    LogicalOperator,
    PolicyCategory,
    PolicyEffect,
    PolicyType,
    ResourceType,
    RuleOperator,
)
from app.rules.engine import Condition, Rule


@dataclass(frozen=True, slots=True)
class GuardrailTemplate:
    """One shipped policy, ready to seed."""

    slug: str
    name: str
    description: str
    category: PolicyCategory
    policy_type: PolicyType
    effect: PolicyEffect
    rule: Rule
    priority: int = 900
    resource_types: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    subject_types: list[str] = field(default_factory=list)
    obligations: dict[str, Any] = field(default_factory=dict)
    risk_weight: float = 0.5
    standard: ComplianceStandard = ComplianceStandard.SECURITY


def _condition(
    source: AttributeSource,
    path: str,
    operator: RuleOperator,
    value: Any = None,
    *,
    negate: bool = False,
) -> Condition:
    return Condition(source=source, path=path, operator=operator, value=value, negate=negate)


BUILTIN_GUARDRAILS: tuple[GuardrailTemplate, ...] = (
    GuardrailTemplate(
        slug="deny-secret-export",
        name="Secrets may not be exported",
        description=(
            "Exporting a secret moves it out of the store that protects it and into "
            "a file that nothing does. There is no configuration under which this is "
            "the right operation, so it is refused rather than gated."
        ),
        category=PolicyCategory.SECRETS,
        policy_type=PolicyType.RESOURCE_BASED,
        effect=PolicyEffect.DENY,
        resource_types=[str(ResourceType.SECRET)],
        actions=[str(ActionType.EXPORT), str(ActionType.SHARE)],
        rule=Rule(
            name="always",
            conditions=[_condition(AttributeSource.ACTION, "name", RuleOperator.EXISTS)],
        ),
        priority=1_000,
        risk_weight=1.0,
    ),
    GuardrailTemplate(
        slug="require-approval-production-delete",
        name="Deleting production infrastructure needs approval",
        description=(
            "A delete against a production asset is the operation with the shortest "
            "path from one mistake to an outage, and the one least likely to be "
            "reversible. Gated rather than denied: it is a legitimate thing to do, "
            "just not alone and not by accident."
        ),
        category=PolicyCategory.INFRASTRUCTURE,
        policy_type=PolicyType.APPROVAL,
        effect=PolicyEffect.REQUIRE_APPROVAL,
        resource_types=[str(ResourceType.INFRASTRUCTURE_ASSET)],
        actions=[str(ActionType.DELETE)],
        rule=Rule(
            name="production",
            conditions=[
                _condition(
                    AttributeSource.RESOURCE,
                    "environment",
                    RuleOperator.IN,
                    ["prod", "production"],
                )
            ],
        ),
        obligations={"approval_type": "single", "levels": 1},
        priority=900,
        risk_weight=0.9,
    ),
    GuardrailTemplate(
        slug="deny-expired-authentication",
        name="An expired or absent authentication is not a caller",
        description=(
            "Every decision reads the caller's authentication state. Without this "
            "guardrail an unauthenticated request is simply one whose subject "
            "attributes are missing, and a policy written in terms of what a subject "
            "*is* would not notice."
        ),
        category=PolicyCategory.SECURITY,
        policy_type=PolicyType.CONTEXT_AWARE,
        effect=PolicyEffect.DENY,
        rule=Rule(
            name="unauthenticated",
            logical_operator=LogicalOperator.ANY,
            conditions=[
                _condition(AttributeSource.CONTEXT, "authenticated", RuleOperator.NOT_EXISTS),
                _condition(AttributeSource.CONTEXT, "authenticated", RuleOperator.EQUALS, False),
            ],
        ),
        priority=1_000,
        risk_weight=1.0,
    ),
    GuardrailTemplate(
        slug="require-mfa-for-manage",
        name="Administrative management requires MFA",
        description=(
            "Manage is the action that grants other actions. Requiring a second "
            "factor for it is what stops one stolen session from becoming permanent "
            "access."
        ),
        category=PolicyCategory.SECURITY,
        policy_type=PolicyType.CONTEXT_AWARE,
        effect=PolicyEffect.REQUIRE_MFA,
        actions=[str(ActionType.MANAGE)],
        rule=Rule(
            name="no-mfa",
            conditions=[
                _condition(
                    AttributeSource.CONTEXT,
                    "authentication_method",
                    RuleOperator.NOT_IN,
                    ["mfa", "webauthn", "totp"],
                )
            ],
        ),
        obligations={"methods": ["totp", "webauthn"]},
        priority=850,
        risk_weight=0.7,
    ),
    GuardrailTemplate(
        slug="deny-cross-organization-access",
        name="A subject may not reach another organization's resources",
        description=(
            "Tenant isolation, expressed as policy so it is visible and auditable "
            "rather than only implicit in every service's queries. Belt and braces "
            "with the scoping each service already does -- this is the one invariant "
            "worth stating twice."
        ),
        category=PolicyCategory.ORGANIZATION,
        policy_type=PolicyType.ABAC,
        effect=PolicyEffect.DENY,
        rule=Rule(
            name="mismatched-organization",
            conditions=[
                # An attribute-to-attribute comparison, which is the only
                # way to say this: there is no literal that means
                # "whatever the caller's organization happens to be".
                # Writing it as a literal would produce one policy per
                # tenant, which is not governance but a copy of the
                # tenant table.
                Condition(
                    source=AttributeSource.RESOURCE,
                    path="organization_id",
                    operator=RuleOperator.NOT_EQUALS,
                    value_source=AttributeSource.SUBJECT,
                    value_path="organization_id",
                    description=(
                        "The resource belongs to a different organization than the caller."
                    ),
                ),
            ],
        ),
        priority=1_000,
        risk_weight=1.0,
    ),
    GuardrailTemplate(
        slug="deny-maintenance-window-deploys",
        name="No deploys during a declared freeze",
        description=(
            "A change freeze that relies on everyone remembering is not a freeze. "
            "Soft by design -- it denies, and an operator who genuinely must deploy "
            "raises a scoped, expiring exception, which leaves a record of who "
            "decided and why."
        ),
        category=PolicyCategory.CONFIGURATION,
        policy_type=PolicyType.TIME_BASED,
        effect=PolicyEffect.DENY,
        actions=[str(ActionType.DEPLOY)],
        rule=Rule(
            name="in-freeze",
            conditions=[
                _condition(AttributeSource.ENVIRONMENT, "change_freeze", RuleOperator.EQUALS, True)
            ],
        ),
        priority=800,
        risk_weight=0.6,
        standard=ComplianceStandard.CONFIGURATION,
    ),
)
"""Every policy a fresh organization starts with.

Six, all at high priority, all ``is_system``. Each one is here because
its absence names a specific incident: exported secrets, an accidental
production delete, an unauthenticated caller that looked merely
attribute-less, a stolen session that could grant itself more access, a
cross-tenant read, and a deploy during a freeze.
"""


def guardrails_for(category: PolicyCategory | None = None) -> list[GuardrailTemplate]:
    """The shipped guardrails, optionally narrowed to one category."""
    if category is None:
        return list(BUILTIN_GUARDRAILS)
    return [one for one in BUILTIN_GUARDRAILS if one.category is category]


__all__ = ["BUILTIN_GUARDRAILS", "GuardrailTemplate", "guardrails_for"]
