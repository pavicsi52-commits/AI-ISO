"""Enterprise Validation Framework.

Every API, DTO, configuration, business rule, database request, workflow,
and connector uses this framework (docs/016_Enterprise_Validation_Framework.md.txt).
No validation logic is duplicated -- field-level rules reuse
:mod:`shared_core.validators` (Prompt 012); security rules reuse
:mod:`shared_core.security` (Prompt 012/017).
"""

from shared_core.validation.base import ValidationLayer, ValidationRule, ValidationSeverity
from shared_core.validation.constants import ValidationFrameworkConstants
from shared_core.validation.context import ValidationContext
from shared_core.validation.exceptions import ValidationPipelineError, ValidatorNotFoundError
from shared_core.validation.factory import build_pipeline, create_manager_with_defaults
from shared_core.validation.manager import ValidationManager, default_manager
from shared_core.validation.pipeline import LayerStep, ValidationPipeline
from shared_core.validation.results import PipelineResult, ValidationResult
from shared_core.validation.validator import Validator

__all__ = [
    "LayerStep",
    "PipelineResult",
    "ValidationContext",
    "ValidationFrameworkConstants",
    "ValidationLayer",
    "ValidationManager",
    "ValidationPipeline",
    "ValidationPipelineError",
    "ValidationResult",
    "ValidationRule",
    "ValidationSeverity",
    "Validator",
    "ValidatorNotFoundError",
    "build_pipeline",
    "create_manager_with_defaults",
    "default_manager",
]
