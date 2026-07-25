"""Validation-framework-internal exceptions.

Per docs/016_Enterprise_Validation_Framework.md.txt "ERROR FORMAT": actual
validation *failures* are reported via
:class:`shared_core.exceptions.ValidationError`/``BusinessRuleError``/etc
through the standard Prompt 006 envelope -- "Never invent custom
validation responses". These two exceptions are different: they're
*framework misconfiguration* errors (an unregistered layer or validator
requested), not validation failures, so they subclass
:class:`shared_core.exceptions.base.AIIOSException` directly rather than
:class:`shared_core.exceptions.ValidationError`.
"""

from __future__ import annotations

from shared_core.exceptions.base import AIIOSException


class ValidationPipelineError(AIIOSException):
    """Raised when the validation pipeline itself is misconfigured."""

    error_code = "AIIOS-VALPIPE-0001"
    status_code = 500
    severity = "high"
    retryable = False
    default_user_message = "A validation error occurred. Please contact support."


class ValidatorNotFoundError(AIIOSException):
    """Raised when a named validator or rule isn't registered."""

    error_code = "AIIOS-VALPIPE-0002"
    status_code = 500
    severity = "high"
    retryable = False
    default_user_message = "A validation error occurred. Please contact support."
