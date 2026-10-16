"""
Razorpay client wrapper — orders + refunds. Async via httpx.

The refund API is NEVER called from a request handler (project.mdc rule 4);
only the refund worker calls create_refund. Order creation IS called inside the
booking transaction BEFORE commit (spec DISPATCH_FLOW step 2c) with a tight
timeout so it cannot pin a PgBouncer server connection indefinitely.
"""
from __future__ import annotations

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()
settings = get_settings()

_BASE = "https://api.razorpay.com/v1"
# Tight budget: the order call runs inside the booking txn (holds a server conn
# under PgBouncer transaction mode). Keep it short; fail closed on timeout.
_TIMEOUT = httpx.Timeout(connect=2.0, read=4.0, write=2.0, pool=2.0)


class RazorpayError(Exception):
    pass


class RazorpayRefundError(Exception):
    """Base for refund worker classification (sync refund API only)."""


class RazorpayRefundPermanentError(RazorpayRefundError):
    """Non-retriable Razorpay/client error — ops must intervene."""


class RazorpayRefundRetryableError(RazorpayRefundError):
    """Transient or in-flight — worker may backoff and retry."""


REFUND_IDEMPOTENCY_HEADER = "X-Refund-Idempotency"


def _auth() -> tuple[str, str]:
    return (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)


async def create_order(*, amount_paise: int, receipt: str, notes: dict | None = None) -> str:
    """Create a Razorpay order for amount_due_online only. Returns order id."""
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,
    }
    if notes:
        payload["notes"] = notes
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{_BASE}/orders", json=payload, auth=_auth())
        resp.raise_for_status()
        return resp.json()["id"]
    except (httpx.HTTPError, KeyError) as exc:
        log.error("razorpay_order_failed", error=str(exc))
        raise RazorpayError(str(exc)) from exc


def _refund_error_body(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                return str(err.get("description") or err.get("code") or resp.text)[:500]
    except ValueError:
        pass
    return (resp.text or f"HTTP {resp.status_code}")[:500]


def create_refund_sync(*, payment_gateway_id: str, amount_paise: int, idempotency_key: str) -> str:
    """SYNC refund call for the Celery refund worker. idempotency_key = refunds.id
    (client-generated, stable across retries). Returns gateway refund id."""
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            resp = client.post(
                f"{_BASE}/payments/{payment_gateway_id}/refund",
                json={"amount": amount_paise},
                headers={REFUND_IDEMPOTENCY_HEADER: idempotency_key},
                auth=_auth(),
            )
    except httpx.TimeoutException as exc:
        raise RazorpayRefundRetryableError(str(exc)) from exc
    except httpx.RequestError as exc:
        raise RazorpayRefundRetryableError(str(exc)) from exc

    if 200 <= resp.status_code < 300:
        try:
            return resp.json()["id"]
        except (KeyError, ValueError, TypeError) as exc:
            raise RazorpayRefundPermanentError(f"invalid refund response: {exc}") from exc

    detail = _refund_error_body(resp)
    code = resp.status_code
    if code in (408, 429) or code >= 500:
        raise RazorpayRefundRetryableError(detail)
    if code == 409:
        # Prior request still processing — retry same key + body (Razorpay idempotent refund).
        raise RazorpayRefundRetryableError(detail)
    if 400 <= code < 500:
        raise RazorpayRefundPermanentError(detail)
    raise RazorpayRefundRetryableError(detail)
