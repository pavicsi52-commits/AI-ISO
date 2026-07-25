"""Pure utility helper functions. See docs/012_Shared_Core_Framework.md.txt."""

from shared_core.helpers.collection_helper import chunk, deduplicate, first, flatten
from shared_core.helpers.compression_helper import (
    gzip_compress,
    gzip_decompress,
    zlib_compress,
    zlib_decompress,
)
from shared_core.helpers.date_helper import (
    days_between,
    from_iso8601,
    is_expired,
    to_iso8601,
    utcnow,
)
from shared_core.helpers.environment_helper import (
    get_env,
    get_env_bool,
    get_env_int,
    is_running_in_container,
)
from shared_core.helpers.file_helper import get_extension, human_readable_size, is_safe_filename
from shared_core.helpers.hash_helper import sha256_hex, stable_hash
from shared_core.helpers.json_helper import from_json, safe_from_json, to_json
from shared_core.helpers.retry_helper import retry_async
from shared_core.helpers.string_helper import mask_string, slugify, to_snake_case, truncate
from shared_core.helpers.time_helper import Stopwatch, measure_ms
from shared_core.helpers.uuid_helper import generate_uuid, is_valid_uuid, short_uuid

__all__ = [
    "Stopwatch",
    "chunk",
    "days_between",
    "deduplicate",
    "first",
    "flatten",
    "from_iso8601",
    "from_json",
    "generate_uuid",
    "get_env",
    "get_env_bool",
    "get_env_int",
    "get_extension",
    "gzip_compress",
    "gzip_decompress",
    "human_readable_size",
    "is_expired",
    "is_running_in_container",
    "is_safe_filename",
    "is_valid_uuid",
    "mask_string",
    "measure_ms",
    "retry_async",
    "safe_from_json",
    "sha256_hex",
    "short_uuid",
    "slugify",
    "stable_hash",
    "to_iso8601",
    "to_json",
    "to_snake_case",
    "truncate",
    "utcnow",
    "zlib_compress",
    "zlib_decompress",
]
