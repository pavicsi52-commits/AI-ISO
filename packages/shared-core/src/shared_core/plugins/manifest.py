"""Plugin manifest.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN MANIFEST":
Plugin ID, Name, Version, Author, Vendor, Description, License,
Category, Dependencies, Permissions, Compatibility, Entry Point,
Configuration Schema. Also "SECURITY"/"MARKETPLACE": Code Signing,
Digital Signatures -- reuses ``cryptography``'s RSA-PSS/SHA-256
directly (the same library, and the same
:func:`shared_core.security.encryption.generate_rsa_keypair` keypair
shape, already vetted by Prompt 017's security framework) rather than a
new signing dependency.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, cast

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from shared_core.plugins.dependency import PluginDependency
from shared_core.plugins.exceptions import InvalidManifestError, SignatureVerificationError
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.permissions import PluginPermission

_SIGNATURE_PADDING = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
)


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """A plugin's complete declared contract."""

    metadata: PluginMetadata
    entry_point: str
    dependencies: tuple[PluginDependency, ...] = field(default_factory=tuple)
    permissions: frozenset[PluginPermission] = field(default_factory=frozenset)
    compatibility: str = "*"
    configuration_schema: dict[str, Any] = field(default_factory=dict)
    signature: str | None = None


def _require(data: dict[str, Any], key: str) -> Any:
    try:
        return data[key]
    except KeyError as exc:
        raise InvalidManifestError(f"Plugin manifest is missing required field {key!r}.") from exc


def parse_manifest_dict(data: dict[str, Any]) -> PluginManifest:
    """Parse a plugin manifest from a plain ``dict`` ("Every plugin shall declare metadata").

    Raises:
        InvalidManifestError: If a required field is missing or a value has the wrong shape.
    """
    try:
        metadata = PluginMetadata(
            plugin_id=_require(data, "plugin_id"),
            name=_require(data, "name"),
            version=_require(data, "version"),
            category=PluginType(_require(data, "category")),
            author=data.get("author"),
            vendor=data.get("vendor"),
            description=data.get("description"),
            license=data.get("license"),
            homepage=data.get("homepage"),
            tags=tuple(data.get("tags", ())),
        )
        dependencies = tuple(
            PluginDependency(
                depends_on_plugin_id=entry["plugin_id"],
                version_constraint=entry.get("version_constraint", "*"),
                optional=entry.get("optional", False),
            )
            for entry in data.get("dependencies", ())
        )
        permissions = frozenset(PluginPermission(p) for p in data.get("permissions", ()))
        return PluginManifest(
            metadata=metadata,
            entry_point=_require(data, "entry_point"),
            dependencies=dependencies,
            permissions=permissions,
            compatibility=data.get("compatibility", "*"),
            configuration_schema=data.get("configuration_schema", {}),
            signature=data.get("signature"),
        )
    except InvalidManifestError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise InvalidManifestError(f"Plugin manifest is malformed: {exc}") from exc


def parse_manifest_json(text: str) -> PluginManifest:
    """Parse a plugin manifest from a JSON string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidManifestError(f"Plugin manifest is not valid JSON: {exc}") from exc
    return parse_manifest_dict(data)


def parse_manifest_yaml(text: str) -> PluginManifest:
    """Parse a plugin manifest from a YAML string."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InvalidManifestError(f"Plugin manifest is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidManifestError("Plugin manifest YAML must decode to a mapping.")
    return parse_manifest_dict(data)


def manifest_to_dict(manifest: PluginManifest, *, include_signature: bool = True) -> dict[str, Any]:
    """Render *manifest* back to a plain ``dict`` (the inverse of :func:`parse_manifest_dict`)."""
    data: dict[str, Any] = {
        "plugin_id": manifest.metadata.plugin_id,
        "name": manifest.metadata.name,
        "version": manifest.metadata.version,
        "category": manifest.metadata.category.value,
        "author": manifest.metadata.author,
        "vendor": manifest.metadata.vendor,
        "description": manifest.metadata.description,
        "license": manifest.metadata.license,
        "homepage": manifest.metadata.homepage,
        "tags": list(manifest.metadata.tags),
        "entry_point": manifest.entry_point,
        "dependencies": [
            {
                "plugin_id": dependency.depends_on_plugin_id,
                "version_constraint": dependency.version_constraint,
                "optional": dependency.optional,
            }
            for dependency in manifest.dependencies
        ],
        "permissions": sorted(permission.value for permission in manifest.permissions),
        "compatibility": manifest.compatibility,
        "configuration_schema": manifest.configuration_schema,
    }
    if include_signature:
        data["signature"] = manifest.signature
    return data


def _canonical_bytes(manifest: PluginManifest) -> bytes:
    payload = manifest_to_dict(manifest, include_signature=False)
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def sign_manifest(manifest: PluginManifest, *, private_key: str) -> str:
    """Sign *manifest* with an RSA private key (PEM), returning a base64 signature.

    The signature covers every field except ``signature`` itself
    ("Code Signing"). Pair with
    :func:`shared_core.security.encryption.generate_rsa_keypair` to
    generate a keypair.
    """
    key = cast(
        rsa.RSAPrivateKey,
        serialization.load_pem_private_key(private_key.encode("ascii"), password=None),
    )
    signature = key.sign(_canonical_bytes(manifest), _SIGNATURE_PADDING, hashes.SHA256())
    return base64.urlsafe_b64encode(signature).decode("ascii")


def verify_manifest_signature(manifest: PluginManifest, *, public_key: str) -> bool:
    """Verify *manifest*'s signature against an RSA public key (PEM).

    Returns ``False`` (rather than raising) for a missing or malformed
    signature -- signature data originates from an untrusted plugin
    bundle, so "doesn't verify" and "isn't even shaped like a signature"
    are the same outcome to a caller.
    """
    if manifest.signature is None:
        return False
    key = cast(rsa.RSAPublicKey, serialization.load_pem_public_key(public_key.encode("ascii")))
    try:
        signature = base64.urlsafe_b64decode(manifest.signature)
    except (ValueError, TypeError):
        return False
    try:
        key.verify(signature, _canonical_bytes(manifest), _SIGNATURE_PADDING, hashes.SHA256())
    except InvalidSignature:
        return False
    return True


def require_valid_signature(manifest: PluginManifest, *, public_key: str) -> None:
    """Raise unless *manifest*'s signature verifies against *public_key*.

    Raises:
        SignatureVerificationError: If the signature is missing or does not verify.
    """
    if not verify_manifest_signature(manifest, public_key=public_key):
        raise SignatureVerificationError(
            f"Plugin {manifest.metadata.plugin_id!r}'s signature could not be verified."
        )


__all__ = [
    "PluginManifest",
    "manifest_to_dict",
    "parse_manifest_dict",
    "parse_manifest_json",
    "parse_manifest_yaml",
    "require_valid_signature",
    "sign_manifest",
    "verify_manifest_signature",
]
