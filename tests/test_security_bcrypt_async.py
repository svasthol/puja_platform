"""Async bcrypt wrappers match sync primitives."""
from __future__ import annotations

import pytest

from app.core.security import hash_secret, hash_secret_async, verify_secret, verify_secret_async


@pytest.mark.asyncio
async def test_verify_secret_async_matches_sync():
    hashed = hash_secret("unit-test-secret")
    assert await verify_secret_async("unit-test-secret", hashed) is True
    assert await verify_secret_async("wrong", hashed) is False
    assert verify_secret("unit-test-secret", hashed) is True


@pytest.mark.asyncio
async def test_hash_secret_async_matches_sync():
    a = await hash_secret_async("same-input")
    b = hash_secret("same-input")
    assert await verify_secret_async("same-input", a)
    assert verify_secret("same-input", b)
