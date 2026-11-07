#!/usr/bin/env python3
"""Verify production Python deps on Linux (staging/prod). Exit 0 if all imports OK."""

from __future__ import annotations

import platform
import sys

MIN_PYTHON = (3, 12)
MAX_PYTHON = (3, 13)  # exclusive upper: 3.12.x only per pyproject requires-python


def _version_ok() -> None:
    v = sys.version_info[:3]
    if v < MIN_PYTHON or v >= MAX_PYTHON:
        raise SystemExit(
            f"Python {v[0]}.{v[1]} not in supported range "
            f"[{MIN_PYTHON[0]}.{MIN_PYTHON[1]}, {MAX_PYTHON[0]}.{MAX_PYTHON[1]})"
        )


def _import_many(modules: list[str]) -> None:
    failed: list[str] = []
    for name in modules:
        try:
            __import__(name)
        except Exception as exc:  # noqa: BLE001 — report all import failures
            failed.append(f"{name}: {exc}")
    if failed:
        raise SystemExit("Import failures:\n  " + "\n  ".join(failed))


def main() -> None:
    print(
        f"platform={platform.system()} machine={platform.machine()} "
        f"python={platform.python_version()}"
    )
    if platform.system() == "Windows":
        print("WARN: running on Windows — use this script on Linux staging/prod or CI arm64 job")

    _version_ok()

    # Production stack from pyproject.toml (runtime only)
    _import_many(
        [
            "fastapi",
            "uvicorn",
            "orjson",
            "pydantic",
            "pydantic_settings",
            "sqlalchemy",
            "alembic",
            "psycopg",
            "psycopg_pool",
            "celery",
            "kombu",
            "redis",
            "jwt",  # PyJWT
            "bcrypt",
            "multipart",
            "cryptography",
            "httpx",
            "boto3",
            "structlog",
            "prometheus_client",
            "ulid",
        ]
    )

    # uvicorn[standard] extras (Linux only — not installed on Windows wheels set)
    if platform.system() != "Windows":
        _import_many(["httptools", "uvloop"])

    print("linux_runtime: OK")


if __name__ == "__main__":
    main()
