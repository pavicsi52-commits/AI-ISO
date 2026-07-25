"""HTTP method enumeration."""

from enum import StrEnum


class HttpMethod(StrEnum):
    """Supported HTTP methods, per docs/006_API_Design_Master.md.txt."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
