"""
FCM push client (P-NOTIFY) — Firebase Cloud Messaging HTTP v1 API.

Authenticates with a service-account JSON (`FCM_SERVICE_ACCOUNT_PATH`).
Legacy `FCM_SERVER_KEY` is supported only as a fallback for older Firebase projects.

Best-effort by design; partner poll is the safety net. Returns structured
results so callers can delete UNREGISTERED device tokens.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import jwt
import structlog

from app.core.config import get_settings

log = structlog.get_logger()
settings = get_settings()

_FCM_V1_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_LEGACY_FCM_URL = "https://fcm.googleapis.com/fcm/send"
_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
_UNREGISTERED_ERRORS = frozenset(
    {
        "NotRegistered",
        "InvalidRegistration",
        "MismatchSenderId",
        "UNREGISTERED",
        "NOT_FOUND",
    }
)

# Must match partner MainActivity notification channels + res/raw sound files.
_PARTNER_OFFER_CHANNEL_INSTANT = "mana_guruji_offers_high"
_SOUND_OFFER_INSTANT = "offer_instant_bell"

_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


class FcmOutcome(str, Enum):
    SENT = "sent"
    UNREGISTERED = "unregistered"
    FAILED = "failed"
    SKIPPED = "skipped"  # no credentials configured


@dataclass(frozen=True)
class FcmResult:
    outcome: FcmOutcome
    message_id: str | None = None
    error: str | None = None


def _service_account_path() -> Path | None:
    raw = (settings.FCM_SERVICE_ACCOUNT_PATH or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        log.warning("fcm_service_account_missing", path=str(path))
        return None
    return path


def _load_service_account() -> dict[str, Any] | None:
    path = _service_account_path()
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("fcm_service_account_invalid", path=str(path), error=str(exc))
        return None


def _fetch_access_token(sa: dict[str, Any]) -> str | None:
    private_key = sa.get("private_key")
    client_email = sa.get("client_email")
    if not private_key or not client_email:
        log.warning("fcm_service_account_incomplete")
        return None
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": client_email,
            "sub": client_email,
            "aud": _OAUTH_TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
            "scope": _FCM_V1_SCOPE,
        },
        private_key,
        algorithm="RS256",
    )
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _OAUTH_TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.warning("fcm_oauth_token_failed", error=str(exc))
        return None
    token = data.get("access_token")
    if not token:
        return None
    expires_in = int(data.get("expires_in", 3600))
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = time.time() + max(expires_in - 60, 60)
    return token


def _access_token() -> str | None:
    if _token_cache["access_token"] and time.time() < float(_token_cache["expires_at"]):
        return str(_token_cache["access_token"])
    sa = _load_service_account()
    if sa is None:
        return None
    return _fetch_access_token(sa)


def _v1_send_url(project_id: str) -> str:
    return f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


def _android_priority(priority: str) -> str:
    return "HIGH" if priority == "high" else "NORMAL"


def _android_message_config(
    priority: str,
    *,
    channel_id: str | None = None,
    sound: str | None = None,
) -> dict[str, Any]:
    """Android FCM config — custom channel + raw sound per offer type."""
    config: dict[str, Any] = {"priority": _android_priority(priority)}
    notification: dict[str, Any] = {}
    if channel_id:
        notification["channel_id"] = channel_id
    if sound:
        notification["sound"] = sound
    if notification:
        config["notification"] = notification
    return config


def _default_android_notification(priority: str) -> tuple[str | None, str | None]:
    """Only instant (high-priority) offers use the custom bell channel."""
    if priority == "high":
        return _PARTNER_OFFER_CHANNEL_INSTANT, _SOUND_OFFER_INSTANT
    return None, None


def _parse_v1_error(body: dict[str, Any]) -> tuple[FcmOutcome, str]:
    err = body.get("error") or {}
    message = str(err.get("message") or "unknown")
    details = err.get("details") or []
    for item in details:
        if not isinstance(item, dict):
            continue
        code = item.get("errorCode")
        if code in _UNREGISTERED_ERRORS:
            return FcmOutcome.UNREGISTERED, str(code)
    status = str(err.get("status") or "")
    if status == "NOT_FOUND" or "UNREGISTERED" in message.upper():
        return FcmOutcome.UNREGISTERED, message
    return FcmOutcome.FAILED, message


def _send_once_v1(
    device_token: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None,
    priority: str = "high",
    android_channel_id: str | None = None,
    android_sound: str | None = None,
) -> FcmResult:
    sa = _load_service_account()
    if sa is None:
        return FcmResult(outcome=FcmOutcome.SKIPPED)
    project_id = sa.get("project_id")
    if not project_id:
        return FcmResult(outcome=FcmOutcome.FAILED, error="service_account_missing_project_id")
    token = _access_token()
    if not token:
        return FcmResult(outcome=FcmOutcome.SKIPPED)

    if android_channel_id is None and android_sound is None:
        android_channel_id, android_sound = _default_android_notification(priority)

    message: dict[str, Any] = {
        "token": device_token,
        "notification": {"title": title, "body": body},
        "android": _android_message_config(
            priority,
            channel_id=android_channel_id,
            sound=android_sound,
        ),
        "apns": {
            "headers": {"apns-priority": "10" if priority == "high" else "5"},
            "payload": {"aps": {"sound": "default"}},
        },
    }
    if data:
        message["data"] = {k: str(v) for k, v in data.items()}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _v1_send_url(str(project_id)),
                json={"message": message},
                headers=headers,
            )
        if resp.status_code == 200:
            body_json = resp.json()
            return FcmResult(outcome=FcmOutcome.SENT, message_id=body_json.get("name"))
        try:
            body_json = resp.json()
        except json.JSONDecodeError:
            body_json = {}
        outcome, err = _parse_v1_error(body_json)
        if outcome == FcmOutcome.UNREGISTERED:
            return FcmResult(outcome=FcmOutcome.UNREGISTERED, error=err)
        return FcmResult(outcome=FcmOutcome.FAILED, error=err or resp.text)
    except httpx.HTTPError as exc:
        return FcmResult(outcome=FcmOutcome.FAILED, error=str(exc))


def _send_once_legacy(
    device_token: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None,
    priority: str = "high",
    android_channel_id: str | None = None,
    android_sound: str | None = None,
) -> FcmResult:
    if not settings.FCM_SERVER_KEY:
        return FcmResult(outcome=FcmOutcome.SKIPPED)
    if android_channel_id is None and android_sound is None:
        android_channel_id, android_sound = _default_android_notification(priority)
    notification: dict[str, Any] = {"title": title, "body": body}
    if android_channel_id:
        notification["android_channel_id"] = android_channel_id
    if android_sound:
        notification["sound"] = android_sound
    payload: dict = {
        "to": device_token,
        "notification": notification,
        "priority": priority,
    }
    if data:
        payload["data"] = data
    headers = {
        "Authorization": f"key={settings.FCM_SERVER_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(_LEGACY_FCM_URL, json=payload, headers=headers)
        resp.raise_for_status()
        body_json = resp.json()
        results = body_json.get("results") or []
        if results:
            first = results[0]
            if "message_id" in first:
                return FcmResult(outcome=FcmOutcome.SENT, message_id=first["message_id"])
            err = first.get("error", "unknown")
            if err in _UNREGISTERED_ERRORS:
                return FcmResult(outcome=FcmOutcome.UNREGISTERED, error=err)
            return FcmResult(outcome=FcmOutcome.FAILED, error=err)
        if body_json.get("success", 0) >= 1:
            return FcmResult(outcome=FcmOutcome.SENT, message_id=body_json.get("message_id"))
        return FcmResult(outcome=FcmOutcome.FAILED, error="no_results")
    except httpx.HTTPError as exc:
        return FcmResult(outcome=FcmOutcome.FAILED, error=str(exc))


def _send_once_sync(
    device_token: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None,
    priority: str = "high",
    android_channel_id: str | None = None,
    android_sound: str | None = None,
) -> FcmResult:
    if _service_account_path() is not None:
        return _send_once_v1(
            device_token,
            title=title,
            body=body,
            data=data,
            priority=priority,
            android_channel_id=android_channel_id,
            android_sound=android_sound,
        )
    return _send_once_legacy(
        device_token,
        title=title,
        body=body,
        data=data,
        priority=priority,
        android_channel_id=android_channel_id,
        android_sound=android_sound,
    )


def send_push_sync(
    device_token: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    priority: str = "high",
    android_channel_id: str | None = None,
    android_sound: str | None = None,
    max_attempts: int = 3,
) -> FcmResult:
    """Send with retries (DISPATCH_FLOW: 2 retries = 3 attempts total)."""
    last = FcmResult(outcome=FcmOutcome.FAILED, error="not_attempted")
    for attempt in range(1, max_attempts + 1):
        last = _send_once_sync(
            device_token,
            title=title,
            body=body,
            data=data,
            priority=priority,
            android_channel_id=android_channel_id,
            android_sound=android_sound,
        )
        if last.outcome in (FcmOutcome.SENT, FcmOutcome.UNREGISTERED, FcmOutcome.SKIPPED):
            return last
        if attempt < max_attempts:
            time.sleep(0.25 * attempt)
    log.warning(
        "fcm_push_exhausted",
        token_tail=device_token[-8:],
        error=last.error,
        attempts=max_attempts,
    )
    return last
