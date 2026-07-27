"""``/validation-categories``, ``/validation-checks``, and
``/validation-rules``.

None of the three has a REST list entry of its own in docs/043 --
added directly, the same "no REST surface for a secondary resource"
shape docs/040/041 already established, except unlike those precedents
(where the secondary resource is genuinely rarely touched), a
:class:`~app.models.validation_profile.ValidationProfile` cannot
reference any check at all without some way to create one first, and
"Rule Engine" is an explicit ACCEPTANCE CRITERIA line -- without these
three endpoints, neither would be reachable by any real caller.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CategorySvc, CheckSvc, CurrentUserId, RuleSvc
from app.models.validation_category import ValidationCategory
from app.models.validation_check import ValidationCheck
from app.models.validation_rule import ValidationRule
from app.schemas.category import ValidationCategoryCreateRequest, ValidationCategoryResponse
from app.schemas.check import ValidationCheckCreateRequest, ValidationCheckResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.rule import ValidationRuleCreateRequest, ValidationRuleResponse

categories_router = APIRouter(prefix="/validation-categories", tags=["Validation Categories"])
checks_router = APIRouter(prefix="/validation-checks", tags=["Validation Checks"])
rules_router = APIRouter(prefix="/validation-rules", tags=["Validation Rules"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def category_to_response(category: ValidationCategory) -> ValidationCategoryResponse:
    return ValidationCategoryResponse(
        id=category.id,
        organization_id=category.organization_id,
        name=category.name,
        description=category.description,
        validation_type=category.validation_type,
    )


def check_to_response(check: ValidationCheck) -> ValidationCheckResponse:
    return ValidationCheckResponse(
        id=check.id,
        organization_id=check.organization_id,
        category_id=check.category_id,
        check_type=check.check_type,
        name=check.name,
        description=check.description,
        collector_key=check.collector_key,
        parameters=check.parameters,
        timeout_seconds=check.timeout_seconds,
        retry_count=check.retry_count,
    )


def rule_to_response(rule: ValidationRule) -> ValidationRuleResponse:
    return ValidationRuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        check_id=rule.check_id,
        name=rule.name,
        description=rule.description,
        condition=rule.condition,
        result_status=rule.result_status,
        severity=rule.severity,
        weight=rule.weight,
        remediation_hint=rule.remediation_hint,
        priority=rule.priority,
        is_active=rule.is_active,
    )


@categories_router.get("", response_model=SuccessResponse[list[ValidationCategoryResponse]])
async def list_categories(
    organization_id: UUID, categories: CategorySvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationCategoryResponse]]:
    """List every validation category in *organization_id*."""
    records = await categories.list_for_org(organization_id)
    data = [category_to_response(record) for record in records]
    return SuccessResponse(message="Validation categories retrieved.", data=data, meta=_meta())


@categories_router.post(
    "", response_model=SuccessResponse[ValidationCategoryResponse], status_code=201
)
async def create_category(
    body: ValidationCategoryCreateRequest, categories: CategorySvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationCategoryResponse]:
    """Create a new validation category."""
    category = await categories.create(
        organization_id=body.organization_id,
        name=body.name,
        description=body.description,
        validation_type=body.validation_type,
    )
    return SuccessResponse(
        message="Validation category created.", data=category_to_response(category), meta=_meta()
    )


@checks_router.get("", response_model=SuccessResponse[list[ValidationCheckResponse]])
async def list_checks(
    organization_id: UUID, checks: CheckSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationCheckResponse]]:
    """List every reusable validation check in *organization_id* ("Reusable Check Libraries")."""
    records = await checks.list_for_org(organization_id)
    data = [check_to_response(record) for record in records]
    return SuccessResponse(message="Validation checks retrieved.", data=data, meta=_meta())


@checks_router.post("", response_model=SuccessResponse[ValidationCheckResponse], status_code=201)
async def create_check(
    body: ValidationCheckCreateRequest, checks: CheckSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationCheckResponse]:
    """Create a new reusable validation check."""
    check = await checks.create(
        organization_id=body.organization_id,
        category_id=body.category_id,
        check_type=body.check_type,
        name=body.name,
        description=body.description,
        collector_key=body.collector_key,
        parameters=body.parameters,
        timeout_seconds=body.timeout_seconds,
        retry_count=body.retry_count,
    )
    return SuccessResponse(
        message="Validation check created.", data=check_to_response(check), meta=_meta()
    )


@rules_router.get("", response_model=SuccessResponse[list[ValidationRuleResponse]])
async def list_rules(
    check_id: UUID, rules: RuleSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationRuleResponse]]:
    """List every active rule for *check_id* ("Rule Engine")."""
    records = await rules.list_for_check(check_id)
    data = [rule_to_response(record) for record in records]
    return SuccessResponse(message="Validation rules retrieved.", data=data, meta=_meta())


@rules_router.post("", response_model=SuccessResponse[ValidationRuleResponse], status_code=201)
async def create_rule(
    body: ValidationRuleCreateRequest, rules: RuleSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationRuleResponse]:
    """Create a new rule against a check's own collected data ("Rule Engine")."""
    rule = await rules.create(
        organization_id=body.organization_id,
        check_id=body.check_id,
        name=body.name,
        description=body.description,
        condition=body.condition,
        result_status=body.result_status,
        severity=body.severity,
        weight=body.weight,
        remediation_hint=body.remediation_hint,
        priority=body.priority,
    )
    return SuccessResponse(
        message="Validation rule created.", data=rule_to_response(rule), meta=_meta()
    )


__all__ = [
    "categories_router",
    "category_to_response",
    "check_to_response",
    "checks_router",
    "rule_to_response",
    "rules_router",
]
