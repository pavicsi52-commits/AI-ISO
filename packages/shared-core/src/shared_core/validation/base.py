"""Core enums and type aliases for the validation framework."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from shared_core.validation.results import ValidationResult


class ValidationLayer(StrEnum):
    """The nine validation layers, in required execution order.

    Per docs/016_Enterprise_Validation_Framework.md.txt "VALIDATION
    LAYERS": Environment -> Configuration -> API -> Schema -> Business ->
    Database -> Permission -> Workflow -> Response.
    """

    ENVIRONMENT = "environment"
    CONFIGURATION = "configuration"
    API = "api"
    SCHEMA = "schema"
    BUSINESS = "business"
    DATABASE = "database"
    PERMISSION = "permission"
    WORKFLOW = "workflow"
    RESPONSE = "response"


class ValidationSeverity(StrEnum):
    """How serious a validation failure is."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@runtime_checkable
class ValidationRule(Protocol):
    """Structural interface every validation rule function satisfies.

    A plain callable taking whatever positional/keyword arguments the
    rule needs and returning a :class:`~shared_core.validation.results.ValidationResult`
    -- deliberately loose (unlike :class:`shared_core.interfaces.validator.ValidatorProtocol`,
    which is for single-value field validators) because business/database/
    workflow rules take varied, rule-specific arguments.
    """

    def __call__(self, *args: object, **kwargs: object) -> ValidationResult: ...
