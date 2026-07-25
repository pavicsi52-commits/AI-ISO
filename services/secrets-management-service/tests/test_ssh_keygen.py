"""Tests for :mod:`app.ssh.keygen`. Fingerprints cross-checked against
``ssh-keygen -lf`` output during live smoke testing; here we assert the
same computation is deterministic and internally consistent.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.models.enums import SSHKeyType
from app.ssh.keygen import compute_fingerprint, generate_ssh_keypair


@pytest.mark.parametrize(
    "key_type,expected_prefix",
    [
        (SSHKeyType.RSA, "ssh-rsa"),
        (SSHKeyType.ECDSA, "ecdsa-sha2-nistp256"),
        (SSHKeyType.ED25519, "ssh-ed25519"),
    ],
)
def test_generate_ssh_keypair_produces_correct_algorithm(
    key_type: SSHKeyType, expected_prefix: str
) -> None:
    private_pem, public_openssh = generate_ssh_keypair(key_type)
    assert private_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert public_openssh.startswith(expected_prefix)


def test_generate_ssh_keypair_produces_distinct_keys() -> None:
    _private_1, public_1 = generate_ssh_keypair(SSHKeyType.ED25519)
    _private_2, public_2 = generate_ssh_keypair(SSHKeyType.ED25519)
    assert public_1 != public_2


def test_private_key_is_loadable_pkcs8() -> None:
    private_pem, _public = generate_ssh_keypair(SSHKeyType.ED25519)
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    assert isinstance(key, ed25519.Ed25519PrivateKey)


def test_compute_fingerprint_is_deterministic() -> None:
    _private, public = generate_ssh_keypair(SSHKeyType.ED25519)
    assert compute_fingerprint(public) == compute_fingerprint(public)


def test_compute_fingerprint_differs_per_key() -> None:
    _p1, public_1 = generate_ssh_keypair(SSHKeyType.ED25519)
    _p2, public_2 = generate_ssh_keypair(SSHKeyType.ED25519)
    assert compute_fingerprint(public_1) != compute_fingerprint(public_2)


def test_compute_fingerprint_matches_sha256_format() -> None:
    _private, public = generate_ssh_keypair(SSHKeyType.RSA)
    fingerprint = compute_fingerprint(public)
    assert fingerprint.startswith("SHA256:")
    assert "=" not in fingerprint  # base64 padding is stripped


def test_compute_fingerprint_rejects_malformed_key() -> None:
    with pytest.raises(ValueError, match="Malformed OpenSSH public key"):
        compute_fingerprint("not-a-valid-key-line")
