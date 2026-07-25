"""Validation manager: the rule engine registry.

Registers named validators per layer and runs them by name, wrapping each
in :class:`~shared_core.validation.validator.Validator` so every result
carries timing and its validator name automatically.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shared_core.validation.base import ValidationLayer
from shared_core.validation.exceptions import ValidatorNotFoundError
from shared_core.validation.results import ValidationResult
from shared_core.validation.validator import Validator


class ValidationManager:
    """Registry of named validators, organized by layer."""

    def __init__(self) -> None:
        self._validators: dict[tuple[ValidationLayer, str], Validator] = {}

    def register(
        self, layer: ValidationLayer, name: str, func: Callable[..., ValidationResult]
    ) -> None:
        """Register a rule function under ``(layer, name)``."""
        self._validators[(layer, name)] = Validator(name=name, func=func, layer=layer.value)

    def is_registered(self, layer: ValidationLayer, name: str) -> bool:
        """Whether a validator is registered under ``(layer, name)``."""
        return (layer, name) in self._validators

    def get(self, layer: ValidationLayer, name: str) -> Validator:
        """Return the registered validator for ``(layer, name)``.

        Raises:
            ValidatorNotFoundError: If nothing is registered under that key.
        """
        key = (layer, name)
        if key not in self._validators:
            raise ValidatorNotFoundError(
                f"No validator named '{name}' registered for layer '{layer.value}'."
            )
        return self._validators[key]

    def run(self, layer: ValidationLayer, name: str, *args: Any, **kwargs: Any) -> ValidationResult:
        """Run a registered validator by ``(layer, name)``."""
        return self.get(layer, name).run(*args, **kwargs)

    def names_for_layer(self, layer: ValidationLayer) -> list[str]:
        """Every validator name registered for a given layer."""
        return [name for registered_layer, name in self._validators if registered_layer == layer]


default_manager = ValidationManager()
