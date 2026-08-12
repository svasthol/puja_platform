"""RFC 6238 TOTP — standard-library only (no pyotp).

Consistent with the project's "use primitives directly" stance (bcrypt direct,
PyJWT not python-jose). Validated against the RFC 6238 Appendix B test vectors
in tests/test_totp.py, so correctness is provable, not assumed.

Google Authenticator / Authy defaults: SHA1, 6 digits, 30s step. verify()
returns the matched absolute time-step so the caller can persist it and reject
replay of the same code within its 30s window (P-ADMIN-AUTH last_used_step).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

_DIGITS_MOD = [10**d for d in range(0, 11)]


def generate_secret(num_bytes: int = 20) -> str:
    """Base32 secret (no padding) — 20 bytes = 160 bits, the RFC-recommended size."""
    raw = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _b32decode(secret: str) -> bytes:
    # Authenticator apps show secrets unpadded and uppercase; be lenient on input.
    s = secret.strip().replace(" ", "").upper()
    pad = (-len(s)) % 8
    return base64.b32decode(s + ("=" * pad))


def _hotp(key: bytes, counter: int, *, digits: int, digest: str) -> str:
    msg = struct.pack(">Q", counter)
    hs = hmac.new(key, msg, getattr(hashlib, digest)).digest()
    offset = hs[-1] & 0x0F
    binary = struct.unpack(">I", hs[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % _DIGITS_MOD[digits]).zfill(digits)


def totp_at(
    secret: str,
    *,
    at: int | None = None,
    step: int = 30,
    digits: int = 6,
    digest: str = "sha1",
) -> str:
    """Code for a given unix time (defaults to now)."""
    now = int(time.time()) if at is None else int(at)
    counter = now // step
    return _hotp(_b32decode(secret), counter, digits=digits, digest=digest)


def verify(
    secret: str,
    code: str,
    *,
    at: int | None = None,
    step: int = 30,
    digits: int = 6,
    digest: str = "sha1",
    window: int = 1,
) -> int | None:
    """Constant-time verify across ±window steps for clock skew.

    Returns the matched absolute time-step (int) on success, else None. The
    caller persists the step and requires strictly-greater on the next accept
    to block same-code replay within its validity window.
    """
    code = (code or "").strip()
    if not code.isdigit() or len(code) != digits:
        return None
    now = int(time.time()) if at is None else int(at)
    base = now // step
    key = _b32decode(secret)
    for offset in range(-window, window + 1):
        counter = base + offset
        if counter < 0:
            continue
        candidate = _hotp(key, counter, digits=digits, digest=digest)
        if hmac.compare_digest(candidate, code):
            return counter
    return None


def provisioning_uri(secret: str, *, account_name: str, issuer: str, digits: int = 6, step: int = 30) -> str:
    """otpauth:// URI for QR enrolment in an authenticator app."""
    # Keep the issuer:account ':' literal (otpauth convention); encode the rest.
    label = quote(f"{issuer}:{account_name}", safe=":")
    params = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": digits,
            "period": step,
        }
    )
    return f"otpauth://totp/{label}?{params}"
