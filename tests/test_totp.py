"""RFC 6238 TOTP unit tests — no DB, no env. Proves correctness against the
official Appendix B test vectors, plus verify/replay/window behaviour."""
from __future__ import annotations

import base64
import time

from app.core import totp

# RFC 6238 Appendix B — SHA1, 8 digits, secret "12345678901234567890".
_RFC_SECRET = base64.b32encode(b"12345678901234567890").decode("ascii")
_RFC_VECTORS = {
    59: "94287082",
    1111111109: "07081804",
    1111111111: "14050471",
    1234567890: "89005924",
    2000000000: "69279037",
    20000000000: "65353130",
}


def test_rfc6238_vectors():
    for t, expected in _RFC_VECTORS.items():
        assert totp.totp_at(_RFC_SECRET, at=t, digits=8) == expected


def test_generate_secret_is_valid_base32():
    secret = totp.generate_secret()
    # decodes without error and is the expected length (20 bytes -> 32 chars)
    assert len(base64.b32decode(secret + "=" * ((-len(secret)) % 8))) == 20


def test_verify_matches_current_code_and_returns_step():
    secret = totp.generate_secret()
    now = int(time.time())
    code = totp.totp_at(secret, at=now)
    step = totp.verify(secret, code, at=now)
    assert step == now // 30


def test_verify_tolerates_one_step_skew():
    secret = totp.generate_secret()
    now = int(time.time())
    prev_code = totp.totp_at(secret, at=now - 30)
    assert totp.verify(secret, prev_code, at=now, window=1) is not None
    # Two steps out is outside the default window.
    old_code = totp.totp_at(secret, at=now - 90)
    assert totp.verify(secret, old_code, at=now, window=1) is None


def test_verify_rejects_wrong_and_malformed():
    secret = totp.generate_secret()
    now = int(time.time())
    assert totp.verify(secret, "000000", at=now) is None
    assert totp.verify(secret, "12345", at=now) is None      # too short
    assert totp.verify(secret, "abcdef", at=now) is None      # non-digit
    assert totp.verify(secret, "", at=now) is None


def test_replay_step_is_monotonic():
    """The matched step is the replay key: a code is valid only while its step
    is strictly greater than the last accepted one."""
    secret = totp.generate_secret()
    now = int(time.time())
    code = totp.totp_at(secret, at=now)
    first = totp.verify(secret, code, at=now)
    second = totp.verify(secret, code, at=now)
    assert first == second  # same code -> same step; caller rejects the replay


def test_provisioning_uri_shape():
    uri = totp.provisioning_uri("ABCDEF", account_name="+919111111100", issuer="Mana Guruji")
    assert uri.startswith("otpauth://totp/Mana%20Guruji:")
    assert "secret=ABCDEF" in uri
    assert "issuer=Mana+Guruji" in uri
    assert "algorithm=SHA1" in uri and "digits=6" in uri and "period=30" in uri
