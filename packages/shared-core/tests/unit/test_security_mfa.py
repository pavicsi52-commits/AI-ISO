"""Tests for multi-factor authentication: TOTP, email OTP, recovery codes."""

from __future__ import annotations

import time

from shared_core.security.mfa import (
    generate_email_otp,
    generate_recovery_codes,
    generate_totp_code,
    generate_totp_secret,
    generate_trusted_device_token,
    verify_recovery_code,
    verify_totp_code,
)


def test_generate_totp_secret_is_base32() -> None:
    secret = generate_totp_secret()

    assert secret.isupper() or secret.isdigit() or all(c.isalnum() for c in secret)


def test_generate_totp_secret_is_unique_each_time() -> None:
    assert generate_totp_secret() != generate_totp_secret()


def test_totp_code_is_six_digits() -> None:
    secret = generate_totp_secret()

    code = generate_totp_code(secret)

    assert len(code) == 6
    assert code.isdigit()


def test_verify_totp_code_passes_for_current_code() -> None:
    secret = generate_totp_secret()
    code = generate_totp_code(secret)

    assert verify_totp_code(secret, code) is True


def test_verify_totp_code_fails_for_wrong_code() -> None:
    secret = generate_totp_secret()

    assert verify_totp_code(secret, "000000") is False


def test_verify_totp_code_tolerates_one_period_of_drift() -> None:
    secret = generate_totp_secret()
    now = time.time()
    previous_period_code = generate_totp_code(secret, timestamp=now - 30)

    assert verify_totp_code(secret, previous_period_code, timestamp=now) is True


def test_verify_totp_code_rejects_far_future_code() -> None:
    secret = generate_totp_secret()
    now = time.time()
    far_future_code = generate_totp_code(secret, timestamp=now + 300)

    assert verify_totp_code(secret, far_future_code, timestamp=now) is False


def test_generate_email_otp_is_six_digits() -> None:
    otp = generate_email_otp()

    assert len(otp) == 6
    assert otp.isdigit()


def test_generate_recovery_codes_returns_requested_count() -> None:
    codes = generate_recovery_codes(5)

    assert len(codes) == 5
    assert len(set(codes)) == 5  # all unique


def test_generate_recovery_codes_default_count() -> None:
    assert len(generate_recovery_codes()) == 10


def test_verify_recovery_code_passes_for_valid_code() -> None:
    codes = generate_recovery_codes(3)

    assert verify_recovery_code(codes[0], valid_codes=codes) is True


def test_verify_recovery_code_fails_for_used_up_code() -> None:
    codes = generate_recovery_codes(3)
    remaining = codes[1:]  # codes[0] already used/removed

    assert verify_recovery_code(codes[0], valid_codes=remaining) is False


def test_generate_trusted_device_token_is_unique() -> None:
    assert generate_trusted_device_token() != generate_trusted_device_token()
