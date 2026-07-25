"""Plugin validation.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN LIFECYCLE":
Validate. Per "SANDBOX"/"SECURITY": Integrity Verification, Integrity
Validation. Orchestrates the checks every other foundation module
already implements -- manifest structural validity (already enforced
by :func:`~shared_core.plugins.manifest.parse_manifest_dict` itself),
framework-version compatibility (:mod:`~shared_core.plugins.versioning`),
dependency resolution (:mod:`~shared_core.plugins.resolver`), and
signature verification (:mod:`~shared_core.plugins.manifest`) -- into
the single "Validate" lifecycle step. This module adds no new
validation logic of its own.
"""

from __future__ import annotations

from shared_core.plugins.constants import FRAMEWORK_VERSION
from shared_core.plugins.manifest import PluginManifest, require_valid_signature
from shared_core.plugins.resolver import DependencyResolver
from shared_core.plugins.versioning import require_compatible


def validate_manifest(
    manifest: PluginManifest,
    *,
    installed: dict[str, PluginManifest] | None = None,
    public_key: str | None = None,
) -> None:
    """Fully validate *manifest* before it may be installed ("Validate").

    Args:
        manifest: The candidate plugin manifest.
        installed: Every other currently-installed plugin's manifest,
            keyed by id, for dependency resolution -- omit to skip
            dependency validation (e.g. a syntax-only pre-check).
        public_key: An RSA public key (PEM) to verify *manifest*'s
            signature against -- omit to skip signature verification
            ("Digital Signatures" is opt-in per docs/029 "MARKETPLACE",
            not mandatory for every install source).

    Raises:
        VersionIncompatibleError: If *manifest* declares a framework
            compatibility range :data:`FRAMEWORK_VERSION` doesn't satisfy.
        DependencyResolutionError: If a required dependency is missing
            or version-incompatible among *installed*.
        CircularDependencyError: If installing *manifest* would create
            a dependency cycle.
        SignatureVerificationError: If *public_key* is given and
            *manifest*'s signature doesn't verify.
    """
    require_compatible(FRAMEWORK_VERSION, manifest.compatibility, subject="Framework")
    if installed is not None:
        candidates = dict(installed)
        candidates[manifest.metadata.plugin_id] = manifest
        resolver = DependencyResolver(candidates)
        resolver.validate(manifest.metadata.plugin_id)
        resolver.resolve_order()  # raises CircularDependencyError if introduced
    if public_key is not None:
        require_valid_signature(manifest, public_key=public_key)


__all__ = ["validate_manifest"]
