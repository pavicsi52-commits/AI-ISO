"""Tests for :mod:`app.encryption.envelope` -- the crypto-critical
core of this service. Real AES-256-GCM via ``cryptography``, no mocking.
"""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag
from shared_core.security.encryption import decrypt, generate_encryption_key

from app.encryption.envelope import EnvelopeEncryption


@pytest.fixture
def envelope_a() -> EnvelopeEncryption:
    return EnvelopeEncryption(generate_encryption_key())


def test_generate_dek_produces_distinct_keys(envelope_a: EnvelopeEncryption) -> None:
    first = envelope_a.generate_dek()
    second = envelope_a.generate_dek()
    assert first != second


def test_wrap_unwrap_dek_round_trips(envelope_a: EnvelopeEncryption) -> None:
    raw_dek = envelope_a.generate_dek()
    wrapped = envelope_a.wrap_dek(raw_dek)
    assert wrapped != raw_dek
    assert envelope_a.unwrap_dek(wrapped) == raw_dek


def test_encrypt_value_produces_ciphertext_not_plaintext(envelope_a: EnvelopeEncryption) -> None:
    wrapped_dek = envelope_a.wrap_dek(envelope_a.generate_dek())
    ciphertext = envelope_a.encrypt_value("hunter2", wrapped_dek=wrapped_dek)
    assert ciphertext != "hunter2"
    assert "hunter2" not in ciphertext


def test_encrypt_decrypt_round_trips(envelope_a: EnvelopeEncryption) -> None:
    wrapped_dek = envelope_a.wrap_dek(envelope_a.generate_dek())
    ciphertext = envelope_a.encrypt_value("correct horse battery staple", wrapped_dek=wrapped_dek)
    assert envelope_a.decrypt_value(ciphertext, wrapped_dek=wrapped_dek) == (
        "correct horse battery staple"
    )


def test_decrypt_with_wrong_dek_fails(envelope_a: EnvelopeEncryption) -> None:
    wrapped_dek_1 = envelope_a.wrap_dek(envelope_a.generate_dek())
    wrapped_dek_2 = envelope_a.wrap_dek(envelope_a.generate_dek())
    ciphertext = envelope_a.encrypt_value("secret-value", wrapped_dek=wrapped_dek_1)
    with pytest.raises(InvalidTag):
        envelope_a.decrypt_value(ciphertext, wrapped_dek=wrapped_dek_2)


def test_gcm_tamper_detection_rejects_modified_ciphertext(envelope_a: EnvelopeEncryption) -> None:
    wrapped_dek = envelope_a.wrap_dek(envelope_a.generate_dek())
    ciphertext = envelope_a.encrypt_value("tamper-me-not", wrapped_dek=wrapped_dek)
    tampered = ciphertext[:-4] + ("A" if ciphertext[-4] != "A" else "B") + ciphertext[-3:]
    with pytest.raises(Exception):  # noqa: B017 -- either InvalidTag or a base64 padding error
        envelope_a.decrypt_value(tampered, wrapped_dek=wrapped_dek)


def test_rewrap_dek_under_new_master_key(envelope_a: EnvelopeEncryption) -> None:
    raw_dek = envelope_a.generate_dek()
    wrapped_under_old = envelope_a.wrap_dek(raw_dek)
    new_master_key = generate_encryption_key()
    rewrapped = envelope_a.rewrap_dek(wrapped_under_old, new_master_key=new_master_key)
    # The rewrapped blob decrypts correctly under the new master key.
    assert decrypt(rewrapped, key=new_master_key) == raw_dek


def test_reencrypt_value_preserves_plaintext_under_new_dek(
    envelope_a: EnvelopeEncryption,
) -> None:
    old_wrapped_dek = envelope_a.wrap_dek(envelope_a.generate_dek())
    new_wrapped_dek = envelope_a.wrap_dek(envelope_a.generate_dek())
    ciphertext = envelope_a.encrypt_value("rotate-me", wrapped_dek=old_wrapped_dek)

    reencrypted = envelope_a.reencrypt_value(
        ciphertext, old_wrapped_dek=old_wrapped_dek, new_wrapped_dek=new_wrapped_dek
    )

    assert reencrypted != ciphertext
    assert envelope_a.decrypt_value(reencrypted, wrapped_dek=new_wrapped_dek) == "rotate-me"
    with pytest.raises(InvalidTag):
        envelope_a.decrypt_value(reencrypted, wrapped_dek=old_wrapped_dek)


def test_different_master_keys_produce_incompatible_envelopes() -> None:
    envelope_1 = EnvelopeEncryption(generate_encryption_key())
    envelope_2 = EnvelopeEncryption(generate_encryption_key())
    wrapped_dek = envelope_1.wrap_dek(envelope_1.generate_dek())
    with pytest.raises(InvalidTag):
        envelope_2.unwrap_dek(wrapped_dek)
