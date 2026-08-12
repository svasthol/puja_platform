"""
SMS router — ordered provider failover (FAST2SMS ↔ MSG91).

Configure chain via SMS_PROVIDER_ORDER (comma-separated). MSG91 is skipped unless
MSG91_ENABLED=true (hold until DLT + SendOTP template are ready). Widget
tokenAuth / widgetId from the MSG91 OTP Widget UI are NOT used here.

Example .env (no DLT yet):
  SMS_PROVIDER_ORDER=fast2sms,msg91
  MSG91_ENABLED=false
  FAST2SMS_API_KEY=your_dev_api_key

When DLT is ready:
  MSG91_ENABLED=true
  SMS_PROVIDER_ORDER=msg91,fast2sms
"""
from __future__ import annotations

import structlog

from app.core.config import get_settings
from app.services import fast2sms_client, msg91_client
from app.services.sms_types import SmsSendResult

log = structlog.get_logger()
settings = get_settings()


def _provider_chain() -> list[str]:
    raw = settings.SMS_PROVIDER_ORDER or "fast2sms,msg91"
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _try_otp(provider: str, phone: str, otp: str) -> SmsSendResult:
    if provider == "fast2sms":
        if fast2sms_client.send_otp_sms_sync(phone, otp):
            return SmsSendResult(sent=True, provider="fast2sms")
        return SmsSendResult(sent=False, provider="fast2sms", error="fast2sms_otp_failed")
    if provider == "msg91":
        if not settings.MSG91_ENABLED:
            return SmsSendResult(sent=False, provider="msg91", error="msg91_disabled")
        if msg91_client.send_otp_sms_sync(phone, otp):
            return SmsSendResult(sent=True, provider="msg91")
        return SmsSendResult(sent=False, provider="msg91", error="msg91_otp_failed")
    return SmsSendResult(sent=False, provider=provider, error="unknown_provider")


def _try_txn(provider: str, phone: str, message: str) -> SmsSendResult:
    if provider == "fast2sms":
        if fast2sms_client.send_transactional_sms_sync(phone, message):
            return SmsSendResult(sent=True, provider="fast2sms")
        return SmsSendResult(sent=False, provider="fast2sms", error="fast2sms_txn_failed")
    if provider == "msg91":
        if not settings.MSG91_ENABLED:
            return SmsSendResult(sent=False, provider="msg91", error="msg91_disabled")
        if msg91_client.send_transactional_sms_sync(phone, message):
            return SmsSendResult(sent=True, provider="msg91")
        return SmsSendResult(sent=False, provider="msg91", error="msg91_txn_failed")
    return SmsSendResult(sent=False, provider=provider, error="unknown_provider")


def send_otp_sms_sync(phone: str, otp: str) -> SmsSendResult:
    last = SmsSendResult(sent=False, error="no_providers")
    for provider in _provider_chain():
        result = _try_otp(provider, phone, otp)
        if result.sent:
            log.info("sms_otp_sent", provider=provider)
            return result
        last = result
        log.warning("sms_otp_provider_failed", provider=provider, error=result.error)
    log.error("sms_otp_all_providers_failed", phone_tail=phone[-4:])
    return last


async def send_otp_sms(phone: str, otp: str) -> SmsSendResult:
    """Async entry — providers use sync httpx; call is fast enough for auth path."""
    return send_otp_sms_sync(phone, otp)


def send_transactional_sms_sync(phone: str, message: str) -> bool:
    for provider in _provider_chain():
        result = _try_txn(provider, phone, message)
        if result.sent:
            log.info("sms_txn_sent", provider=provider)
            return True
        log.warning("sms_txn_provider_failed", provider=provider, error=result.error)
    log.error("sms_txn_all_providers_failed", phone_tail=phone[-4:])
    return False
