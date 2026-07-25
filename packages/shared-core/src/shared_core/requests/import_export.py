"""Import/export request schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from shared_core.requests.base import BaseRequest
from shared_core.schemas.filtering import FilterParams


class DataFormat(StrEnum):
    """Supported bulk import/export data formats."""

    JSON = "json"
    CSV = "csv"
    YAML = "yaml"


class ImportRequest(BaseRequest):
    """Inbound bulk import request referencing a previously uploaded object."""

    storage_key: str = Field(min_length=1)
    format: DataFormat = DataFormat.JSON
    dry_run: bool = False


class ExportRequest(BaseRequest):
    """Inbound bulk export request."""

    format: DataFormat = DataFormat.JSON
    filters: list[FilterParams] = Field(default_factory=list)
