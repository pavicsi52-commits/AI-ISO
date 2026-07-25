"""Builds validators, pre-populated managers, and pipelines.

The field/request/response rule modules all take a single, uniform kind
of input (a scalar value, a headers mapping, a response payload), so
they're registerable automatically; business/database/security/workflow/
connector rules take varied, use-case-specific arguments and are left for
each service to register explicitly (see the module docstrings under
``shared_core.validation.rules``).
"""

from __future__ import annotations

from shared_core.validation.base import ValidationLayer
from shared_core.validation.manager import ValidationManager
from shared_core.validation.pipeline import ValidationPipeline
from shared_core.validation.rules import field, request, response


def create_manager_with_defaults() -> ValidationManager:
    """Build a :class:`ValidationManager` with every field/request/response
    rule pre-registered under its natural layer.
    """
    manager = ValidationManager()

    for name in _rule_function_names(field):
        manager.register(ValidationLayer.SCHEMA, name, getattr(field, name))
    for name in _rule_function_names(request):
        manager.register(ValidationLayer.API, name, getattr(request, name))
    for name in _rule_function_names(response):
        manager.register(ValidationLayer.RESPONSE, name, getattr(response, name))

    return manager


def _rule_function_names(module: object) -> list[str]:
    return [name for name in dir(module) if name.startswith("validate")]


def build_pipeline(manager: ValidationManager | None = None) -> ValidationPipeline:
    """Build a :class:`ValidationPipeline` bound to *manager* (or a fresh
    manager with defaults registered, if omitted).
    """
    return ValidationPipeline(manager=manager or create_manager_with_defaults())
