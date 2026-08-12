"""Fernet secret-encryption unit tests — round-trip, key rotation, missing key."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core import crypto
from app.core.config import get_settings


@pytest.fixture
def one_key():
    key = Fernet.generate_key().decode()
    settings = get_settings()
    original = settings.TOTP_ENC_KEYS
    settings.TOTP_ENC_KEYS = key
    crypto._keys.cache_clear()
    yield key
    settings.TOTP_ENC_KEYS = original
    crypto._keys.cache_clear()


def test_round_trip(one_key):
    secret = "JBSWY3DPEHPK3PXP"
    token = crypto.encrypt_secret(secret)
    assert token != secret
    assert crypto.decrypt_secret(token) == secret
    assert crypto.current_key_version() == 1


def test_ciphertext_is_nondeterministic(one_key):
    # Fernet embeds a random IV + timestamp — same plaintext, different tokens.
    assert crypto.encrypt_secret("same") != crypto.encrypt_secret("same")


def test_rotation_old_ciphertext_still_decrypts():
    """Encrypt under key A, then rotate so A is second: old token still decrypts,
    new tokens use the new primary key."""
    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()
    settings = get_settings()
    original = settings.TOTP_ENC_KEYS

    settings.TOTP_ENC_KEYS = key_a
    crypto._keys.cache_clear()
    token_a = crypto.encrypt_secret("secret-A")

    # Rotate: new primary is B, A retained for decrypt.
    settings.TOTP_ENC_KEYS = f"{key_b},{key_a}"
    crypto._keys.cache_clear()
    assert crypto.decrypt_secret(token_a) == "secret-A"  # old token still readable
    token_b = crypto.encrypt_secret("secret-B")
    assert crypto.decrypt_secret(token_b) == "secret-B"

    settings.TOTP_ENC_KEYS = original
    crypto._keys.cache_clear()


def test_missing_key_raises():
    settings = get_settings()
    original = settings.TOTP_ENC_KEYS
    settings.TOTP_ENC_KEYS = ""
    crypto._keys.cache_clear()
    try:
        with pytest.raises(crypto.TotpKeyUnavailable):
            crypto.encrypt_secret("x")
    finally:
        settings.TOTP_ENC_KEYS = original
        crypto._keys.cache_clear()
