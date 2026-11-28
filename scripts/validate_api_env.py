#!/usr/bin/env python3
"""Validate api.env / .env against Settings rules and rollout conventions.

Usage:
  python scripts/validate_api_env.py .env
  python scripts/validate_api_env.py /etc/mana-guruji/api.env

Does not print secret values. Exit 0 = OK; 1 = errors (warnings alone still exit 0).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_PLACEHOLDER_SECRET_KEY = "change-me-to-at-least-32-random-chars-openssl-rand-hex-32"


def _parse_env_lines(path: Path) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        rows.append((key.strip(), value.strip(), lineno))
    return rows


def _duplicates(rows: list[tuple[str, str, int]]) -> list[tuple[str, list[int]]]:
    seen: dict[str, list[int]] = {}
    for key, _, lineno in rows:
        seen.setdefault(key.upper(), []).append(lineno)
    return [(k, v) for k, v in seen.items() if len(v) > 1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate api.env for Puja platform API")
    parser.add_argument("env_file", type=Path, help="Path to .env or api.env")
    parser.add_argument(
        "--strict-staging",
        action="store_true",
        help="Fail on staging placeholders (SECRET_KEY, Redis /0, SMS unset)",
    )
    args = parser.parse_args()
    path = args.env_file.expanduser().resolve()
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    rows = _parse_env_lines(path)
    for key, lines in _duplicates(rows):
        errors.append(f"duplicate key {key} at lines {', '.join(map(str, lines))}")

    import os

    from dotenv import load_dotenv

    from app.core.config import get_settings

    load_dotenv(path, override=True, encoding="utf-8")
    get_settings.cache_clear()
    try:
        settings = get_settings()
    except Exception as exc:
        errors.append(f"Settings load failed: {exc}")
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    if not settings.ALLOWED_ORIGINS:
        errors.append("ALLOWED_ORIGINS is empty")
    raw = path.read_text(encoding="utf-8")
    if re.search(r"ALLOWED_ORIGINS\s*=\s*'", raw) and len(settings.ALLOWED_ORIGINS) == 1:
        if "[" not in (settings.ALLOWED_ORIGINS[0] or ""):
            errors.append(
                "ALLOWED_ORIGINS looks mis-quoted for dotenv - use "
                'ALLOWED_ORIGINS=["http://..."]'
            )
    if len(settings.SECRET_KEY) < 32:
        errors.append("SECRET_KEY shorter than 32 characters")
    if settings.SECRET_KEY == _PLACEHOLDER_SECRET_KEY:
        warnings.append("SECRET_KEY is still the documented placeholder — replace before prod")
        if args.strict_staging:
            errors.append("SECRET_KEY placeholder not allowed (--strict-staging)")

    redis_path = str(settings.REDIS_URL).rstrip("/").split("/")[-1]
    if redis_path != "0":
        warnings.append(
            f"REDIS_URL path ends with /{redis_path}; use /0 and set "
            "REDIS_DB_CACHE/CelERY/PRESENCE explicitly"
        )
        if settings.APP_ENV in ("staging", "production"):
            errors.append(f"REDIS_URL must use logical db 0 in path, got /{redis_path}")

    vendor = (settings.KYC_VENDOR or "").strip().lower() or "setu_digilocker"
    from app.services.kyc_vendor import kyc_vendor_configured

    if not (settings.KYC_REDIRECT_URL or "").strip():
        errors.append("KYC_REDIRECT_URL is required for DigiLocker callback")
    if not (settings.KYC_IDENTITY_PEPPER or "").strip():
        errors.append("KYC_IDENTITY_PEPPER is required")

    if not kyc_vendor_configured(vendor):
        errors.append(f"KYC_VENDOR={vendor} is not configured in env (missing credentials)")

    # Staging should have both vendors wired for admin console switch
    if settings.APP_ENV == "staging":
        if not kyc_vendor_configured("apisathi"):
            warnings.append("API Sathi credentials missing — admin cannot switch to apisathi")
        if not kyc_vendor_configured("setu_digilocker"):
            warnings.append("Setu credentials missing — admin cannot switch to setu_digilocker")

    if settings.APP_ENV in ("staging", "production") and settings.DEBUG:
        warnings.append("DEBUG=true on non-dev environment (OTP may leak dev fields)")

    s3_keys = [k for k, _, _ in rows if k.upper().startswith("S3_")]
    access_count = sum(1 for k, _, _ in rows if k.upper() == "S3_ACCESS_KEY")
    if access_count > 1:
        errors.append("multiple S3_ACCESS_KEY lines — use one storage credential block")

    if settings.APP_ENV == "staging" and args.strict_staging:
        if not (settings.FAST2SMS_API_KEY or "").strip() and not settings.MSG91_ENABLED:
            warnings.append("No SMS provider configured; customer OTP needs DEBUG=true or SMS keys")

    for msg in warnings:
        print(f"WARN: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}", file=sys.stderr)

    if errors:
        print(f"\nvalidate_api_env: FAIL ({len(errors)} error(s))", file=sys.stderr)
        return 1
    print(f"validate_api_env: OK — APP_ENV={settings.APP_ENV} KYC_VENDOR={vendor}")
    if warnings:
        print(f"  ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())