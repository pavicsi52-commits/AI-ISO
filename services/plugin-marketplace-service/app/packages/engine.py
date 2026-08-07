"""Plugin package creation, extraction, and checksumming (docs/059
"PACKAGING").

A genuine gap -- no ``shared_core.plugins`` module compresses, archives,
or checksums anything. Builds real ``tar.gz``/``zip`` archives in memory
and computes a real SHA-256 checksum of the packaged bytes, the same
checksum shape ``app/manifests/engine.py``'s own
``compute_manifest_checksum`` and ``playbook-service/app/signing
/signer.py``'s ``sign_checksum`` both already use. Storage of the
resulting bytes is a separate concern, handled by
``shared_core.storage.wrapper.StorageWrapper`` (MinIO) at the service
layer -- this module never touches disk or network.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile
from collections.abc import Mapping

from app.models.enums import PackageFormat


class PackagingError(Exception):
    """A package could not be built or read."""


def build_package(files: Mapping[str, bytes], *, package_format: PackageFormat) -> bytes:
    """Build a real archive in memory from *files* (archive path -> content).

    Raises:
        PackagingError: If *files* is empty.
    """
    if not files:
        raise PackagingError("Cannot package an empty file set.")

    buffer = io.BytesIO()
    if package_format is PackageFormat.ZIP:
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, content in files.items():
                archive.writestr(path, content)
    else:
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for path, content in files.items():
                info = tarfile.TarInfo(name=path)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def extract_package(package_bytes: bytes, *, package_format: PackageFormat) -> dict[str, bytes]:
    """Extract a package back into archive path -> content, for manifest
    re-validation or sandboxed execution.

    Raises:
        PackagingError: If *package_bytes* is not a valid archive of
            *package_format*.
    """
    buffer = io.BytesIO(package_bytes)
    try:
        if package_format is PackageFormat.ZIP:
            with zipfile.ZipFile(buffer) as archive:
                return {name: archive.read(name) for name in archive.namelist()}
        with tarfile.open(fileobj=buffer, mode="r:gz") as archive:
            extracted: dict[str, bytes] = {}
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                handle = archive.extractfile(member)
                if handle is not None:
                    extracted[member.name] = handle.read()
            return extracted
    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        raise PackagingError(f"Corrupt {package_format.value} package: {exc}") from exc


def compute_package_checksum(package_bytes: bytes) -> str:
    """SHA-256 hex digest of a packaged artifact's own raw bytes."""
    return hashlib.sha256(package_bytes).hexdigest()


__all__ = [
    "PackagingError",
    "build_package",
    "compute_package_checksum",
    "extract_package",
]
