"""Setu PAN verify response parsing (no network)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.kyc_types import KycVendorError
from app.services.setu_digilocker_client import SetuDigiLockerClient, normalize_setu_pan_reason


@pytest.mark.asyncio
async def test_verify_pan_success_parses_body():
    client = SetuDigiLockerClient()
    with (
        patch(
            "app.services.setu_digilocker_client._pan_headers",
            return_value={"x-product-instance-id": "test-pan"},
        ),
        patch.object(
            client,
            "_request",
            new=AsyncMock(
                return_value={
                    "verification": "success",
                    "message": "PAN is valid",
                    "traceId": "trace-1",
                    "data": {"full_name": "John Doe", "category": "Individual"},
                }
            ),
        ),
    ):
        result = await client.verify_pan(
            pan="ABCDE1234A",
            consent=True,
            reason="TDS compliance verification for partner onboarding flow",
        )
    assert result.is_success
    assert result.full_name == "John Doe"
    assert result.trace_id == "trace-1"


@pytest.mark.asyncio
async def test_verify_pan_failed_verification():
    client = SetuDigiLockerClient()
    with (
        patch(
            "app.services.setu_digilocker_client._pan_headers",
            return_value={"x-product-instance-id": "test-pan"},
        ),
        patch.object(
            client,
            "_request",
            new=AsyncMock(
                return_value={
                    "verification": "failed",
                    "message": "PAN is invalid",
                }
            ),
        ),
    ):
        result = await client.verify_pan(
            pan="ABCDE1234B",
            consent=True,
            reason="TDS compliance verification for partner onboarding flow",
        )
    assert not result.is_success


@pytest.mark.asyncio
async def test_verify_pan_rejects_short_reason():
    client = SetuDigiLockerClient()
    with pytest.raises(KycVendorError) as exc:
        await client.verify_pan(pan="ABCDE1234A", consent=True, reason="too short")
    assert exc.value.code == "reason_too_short"


def test_normalize_setu_pan_reason_strips_em_dash() -> None:
    raw = "TDS compliance — PAN furnished to e-commerce operator per IT Act."
    normalized = normalize_setu_pan_reason(raw)
    assert "—" not in normalized
    assert "-" in normalized
    assert len(normalized) >= 20


@pytest.mark.asyncio
async def test_verify_pan_sends_ascii_reason_to_setu():
    client = SetuDigiLockerClient()
    mock_request = AsyncMock(
        return_value={
            "verification": "success",
            "message": "PAN is valid",
            "data": {"full_name": "Jane Doe"},
        }
    )
    with (
        patch(
            "app.services.setu_digilocker_client._pan_headers",
            return_value={"x-product-instance-id": "test-pan"},
        ),
        patch.object(client, "_request", new=mock_request),
    ):
        await client.verify_pan(
            pan="ABCDE1234A",
            consent=True,
            reason="TDS compliance — PAN furnished to e-commerce operator per IT Act.",
        )
    sent = mock_request.await_args.kwargs["json"]["reason"]
    assert "—" not in sent
    assert sent.startswith("TDS compliance - PAN")
