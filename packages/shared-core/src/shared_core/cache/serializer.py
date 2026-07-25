"""Value serialization.

Per docs/019_Enterprise_Cache_Framework.md.txt "SERIALIZATION": JSON,
MessagePack, Pickle (Internal Only). "Automatic serialization" --
:mod:`shared_core.cache.manager` picks the format from
:class:`~shared_core.cache.settings.CacheSettings`; callers never
serialize by hand.
"""

from __future__ import annotations

import json
import pickle
from typing import Any

import msgpack

from shared_core.cache.exceptions import SerializationFailedError
from shared_core.cache.settings import SerializationFormat


def serialize(value: Any, *, fmt: SerializationFormat) -> bytes:
    """Serialize *value* to bytes using *fmt*.

    Raises:
        SerializationFailedError: If *value* isn't representable in *fmt*
            (e.g. a non-JSON-serializable object with ``fmt=JSON``).
    """
    try:
        if fmt is SerializationFormat.JSON:
            return json.dumps(value, default=str, separators=(",", ":")).encode("utf-8")
        if fmt is SerializationFormat.MSGPACK:
            return msgpack.packb(value, use_bin_type=True)  # type: ignore[no-any-return]
        # PICKLE: internal only -- never applied to values crossing a trust
        # boundary (see docs/019 "SERIALIZATION": "Pickle (Internal Only)").
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        raise SerializationFailedError(f"Failed to serialize value as {fmt.value}.") from exc


def deserialize(data: bytes, *, fmt: SerializationFormat) -> Any:
    """Deserialize bytes produced by :func:`serialize` back into a value.

    Raises:
        SerializationFailedError: If *data* isn't valid *fmt*.
    """
    try:
        if fmt is SerializationFormat.JSON:
            return json.loads(data.decode("utf-8"))
        if fmt is SerializationFormat.MSGPACK:
            return msgpack.unpackb(data, raw=False)
        return pickle.loads(data)
    except Exception as exc:
        raise SerializationFailedError(f"Failed to deserialize value as {fmt.value}.") from exc


__all__ = ["deserialize", "serialize"]
