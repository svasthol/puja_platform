"""
Razorpay webhook handler (spec DISPATCH_FLOW step 4, API_CONTRACTS webhooks).

Capture/refund logic lives in ``payment_capture`` (REL-004 / REL-015 / REL-005 SSOT).
"""
from __future__ import annotations

from app.services.payment_capture import handle_payment_captured

__all__ = ["handle_payment_captured"]