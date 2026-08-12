"""Symmetric encryption for secrets that must be recoverable (not hashed).

TOTP secrets cannot be hashed — verification needs the plaintext — so they are
Fernet-encrypted at rest (SPEC_AMENDMENTS §19). Fernet = AES-128-CBC + HMAC-SHA256,
authenticated, from the `cryptography` package.

Key management:
  * TOTP_ENC_KEYS is a comma-separated list of urlsafe-base64 Fernet keys.
  * The FIRST key encrypts (current); ALL keys can decrypt (rotation window).
  * Each ciphertext is tagged with a key_version (stored alongside in the DB)
    so rotation never requires re-enrolling every admin at once.

This module NEVER logs plaintext or key material.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings


class TotpKeyUnavailable(RuntimeError):
    """TOTP_ENC_KEYS is not configured — admin TOTP cannot be provisioned/verified."""


@lru_cache
def _keys() -> list[Fernet]:
    raw = get_settings().TOTP_ENC_KEYS.strip()
    if not raw:
        raise TotpKeyUnavailable(
            "TOTP_ENC_KEYS is empty. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and set it in the environment before provisioning admin TOTP."
        )
    keys: list[Fernet] = []
    for k in (part.strip() for part in raw.split(",")):
        if k:
            keys.append(Fernet(k.encode("ascii")))
    if not keys:
        raise TotpKeyUnavailable("TOTP_ENC_KEYS contained no usable keys.")
    return keys


def current_key_version() -> int:
    """1-based index of the encrypting key (the first in TOTP_ENC_KEYS)."""
    _keys()  # validate configured
    return 1


def encrypt_secret(plaintext: str) -> str:
    """Encrypt with the current (first) key. Returns urlsafe token as str."""
    fernet = _keys()[0]
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt, trying every configured key (MultiFernet handles rotation)."""
    mf = MultiFernet(_keys())
    try:
        return mf.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise TotpKeyUnavailable(
            "TOTP secret could not be decrypted with any configured key "
            "(TOTP_ENC_KEYS rotated out or wrong). Provision a new credential."
        ) from exc
