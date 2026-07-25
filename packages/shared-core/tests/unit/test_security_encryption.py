"""Tests for the expanded encryption package: RSA and key rotation."""

from __future__ import annotations

from shared_core.security.encryption import (
    decrypt,
    encrypt,
    generate_encryption_key,
    generate_rsa_keypair,
    rotate_key,
    rsa_decrypt,
    rsa_encrypt,
)


def test_rotate_key_reencrypts_under_new_key() -> None:
    old_key = generate_encryption_key()
    new_key = generate_encryption_key()
    ciphertext = encrypt("top secret", key=old_key)

    rotated = rotate_key(old_key=old_key, new_key=new_key, ciphertext=ciphertext)

    assert decrypt(rotated, key=new_key) == "top secret"


def test_rotate_key_output_cannot_be_decrypted_with_old_key() -> None:
    old_key = generate_encryption_key()
    new_key = generate_encryption_key()
    ciphertext = encrypt("top secret", key=old_key)

    rotated = rotate_key(old_key=old_key, new_key=new_key, ciphertext=ciphertext)

    try:
        decrypt(rotated, key=old_key)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_generate_rsa_keypair_returns_pem_strings() -> None:
    private_key, public_key = generate_rsa_keypair()

    assert "BEGIN PRIVATE KEY" in private_key
    assert "BEGIN PUBLIC KEY" in public_key


def test_rsa_encrypt_decrypt_round_trip() -> None:
    private_key, public_key = generate_rsa_keypair()

    ciphertext = rsa_encrypt("a symmetric key", public_key=public_key)
    plaintext = rsa_decrypt(ciphertext, private_key=private_key)

    assert plaintext == "a symmetric key"


def test_rsa_encrypt_produces_different_ciphertext_each_time() -> None:
    _, public_key = generate_rsa_keypair()

    ciphertext_a = rsa_encrypt("value", public_key=public_key)
    ciphertext_b = rsa_encrypt("value", public_key=public_key)

    assert ciphertext_a != ciphertext_b  # OAEP padding is randomized


def test_rsa_decrypt_fails_with_wrong_private_key() -> None:
    _, public_key = generate_rsa_keypair()
    other_private_key, _ = generate_rsa_keypair()
    ciphertext = rsa_encrypt("value", public_key=public_key)

    try:
        rsa_decrypt(ciphertext, private_key=other_private_key)
        raised = False
    except Exception:
        raised = True
    assert raised
