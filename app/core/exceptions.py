"""
Shared DB exception handling — maps psycopg errors and trigger RAISE EXCEPTIONs
to HTTP responses per spec/API_CONTRACTS.md.

CRITICAL FIX (was P0): under async SQLAlchemy every DB error arrives WRAPPED as
sqlalchemy.exc.DBAPIError (IntegrityError for 23xxx constraint codes, InternalError
for trigger P0001 RAISE EXCEPTIONs). A handler registered on the raw psycopg
classes (psycopg.errors.UniqueViolation, ...) NEVER fires, because
IntegrityError is NOT a subclass of UniqueViolation. We therefore register a
single handler on sqlalchemy.exc.DBAPIError, unwrap `.orig` to the psycopg
error, and dispatch on THAT. Raw-psycopg handlers are also registered so the
same logic works if a worker (sync psycopg) ever raises into an ASGI context.

Every mapped case is driven by SQLSTATE + constraint name / trigger message,
never by fragile isinstance chains alone.
"""
from __future__ import annotations

import re

import orjson
import structlog
from fastapi import HTTPException, Request, status
from fastapi.responses import Response
from psycopg.errors import (
    CheckViolation,
    ExclusionViolation,
    ForeignKeyViolation,
    RaiseException,
    UniqueViolation,
)
from sqlalchemy.exc import DBAPIError

from app.core.redis_client import RedisUnavailable

log = structlog.get_logger()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _unwrap(exc: BaseException) -> BaseException:
    """Return the underlying psycopg error from a SQLAlchemy wrapper, else exc."""
    orig = getattr(exc, "orig", None)
    return orig if orig is not None else exc


def _constraint_name(exc: BaseException) -> str:
    """Prefer psycopg's structured diag.constraint_name; fall back to regex."""
    diag = getattr(exc, "diag", None)
    if diag is not None:
        name = getattr(diag, "constraint_name", None)
        if name:
            return name
    m = re.search(r'constraint "([^"]+)"', str(exc))
    return m.group(1) if m else ""


def _message(exc: BaseException) -> str:
    diag = getattr(exc, "diag", None)
    if diag is not None:
        primary = getattr(diag, "message_primary", None)
        if primary:
            return primary
    return str(exc).split("\n", 1)[0]


def _json(status: int, detail: str, **extra) -> Response:
    body: dict = {"detail": detail}
    body.update(extra)
    return Response(
        content=orjson.dumps(body), status_code=status, media_type="application/json"
    )


# --------------------------------------------------------------------------- #
# The single mapping function — takes the unwrapped psycopg error
# --------------------------------------------------------------------------- #
def map_db_error(pg_exc: BaseException, path: str) -> Response:
    constraint = _constraint_name(pg_exc)
    message = _message(pg_exc)
    msg_l = message.lower()

    log.warning("db_exception", constraint=constraint, message=message, path=path)

    # ---- Unique violations (SQLSTATE 23505) --------------------------------
    if isinstance(pg_exc, UniqueViolation):
        if constraint == "ux_slot_holds_active":
            return _json(409, "That slot was just taken — pick another time.")
        if constraint == "ux_bookings_no_duplicate_submit":
            # Idempotent create. The booking router catches IntegrityError BEFORE
            # this handler and returns the existing booking id. If it reaches
            # here, surface a stable code the client can special-case.
            return _json(409, "duplicate_booking_submit", code="DUPLICATE_SUBMIT")
        if constraint == "payments_idempotency_key_key":
            return _json(200, "already_processed")
        if constraint == "ux_payments_one_success_per_booking":
            # Duplicate successful capture — webhook already recorded one. Ack.
            return _json(200, "already_captured")
        if constraint == "ux_booking_assignments_one_live":
            log.info("duplicate_offer_skipped", constraint=constraint)
            return _json(200, "offer_already_live")
        if constraint == "ux_refunds_one_active_per_payment":
            return _json(200, "refund_already_active")
        return _json(409, "Duplicate record.")

    # ---- Exclusion violations (SQLSTATE 23P01) -----------------------------
    if isinstance(pg_exc, ExclusionViolation):
        if constraint == "ex_bookings_pujari_no_overlap":
            return _json(409, "This overlaps another booking of yours.")
        if constraint == "ex_bookings_intended_no_overlap":
            # Webhook context is handled INSIDE the webhook service (record +
            # auto-refund + 200). If it ever bubbles here from the webhook path,
            # do not 500 — ack Razorpay so it stops retrying.
            if "/webhooks/" in path:
                return _json(200, "auto_refund_initiated")
            return _json(409, "This overlaps a booking reserved for you.")
        return _json(409, "Scheduling conflict.")

    # ---- Trigger RAISE EXCEPTION (SQLSTATE P0001) --------------------------
    if isinstance(pg_exc, RaiseException):
        if "already accepted by a different pujari" in msg_l:
            return _json(409, "This booking was just taken.")
        if "expired at" in msg_l and "can no longer be accepted" in msg_l:
            return _json(410, "This offer has expired.")
        if "already resolved" in msg_l:
            return _json(410, "This offer is no longer available.")
        if "cancelled by the customer" in msg_l:
            return _json(410, "The customer cancelled this booking.")
        if "cannot be cancelled from its current state" in msg_l:
            return _json(409, "This booking can no longer be cancelled — contact support.")
        if "usage limit exceeded" in msg_l:
            return _json(422, "This promo code has reached its limit for your account.")
        if "seed data missing" in msg_l:
            log.error("seed_data_missing", message=message)
            return _json(500, "Deployment configuration error. Operations alerted.")
        if "negative pujari payout refused" in msg_l:
            log.error("negative_payout_config_error", message=message)
            return _json(500, "Payment configuration error. Operations alerted.")
        log.error("unhandled_trigger_exception", message=message)
        return _json(500, "An internal error occurred.")

    # ---- Check / FK --------------------------------------------------------
    if isinstance(pg_exc, CheckViolation):
        return _json(422, "Invalid data for one or more fields.", constraint=constraint)
    if isinstance(pg_exc, ForeignKeyViolation):
        return _json(422, "Referenced record does not exist.")

    log.error("unhandled_db_error", exc=str(pg_exc), constraint=constraint)
    return _json(500, "Database error.")


# --------------------------------------------------------------------------- #
# Registered handlers
# --------------------------------------------------------------------------- #
async def sqlalchemy_db_exception_handler(request: Request, exc: Exception) -> Response:
    """Primary handler: unwrap the SQLAlchemy wrapper, then map the psycopg error."""
    return map_db_error(_unwrap(exc), request.url.path)


async def raw_psycopg_exception_handler(request: Request, exc: Exception) -> Response:
    """Fallback: a raw psycopg error reached the ASGI layer unwrapped."""
    return map_db_error(exc, request.url.path)


async def redis_unavailable_handler(request: Request, exc: RedisUnavailable) -> Response:
    log.warning("redis_unavailable", path=request.url.path, error=str(exc))
    return _json(503, "Cache temporarily unavailable. Please try again.")


# DBAPIError is the common SQLAlchemy base for IntegrityError, InternalError,
# OperationalError, etc. Registering it once covers constraint violations AND
# trigger RAISE EXCEPTIONs. Raw psycopg types are registered defensively.
EXCEPTION_HANDLERS = {
    DBAPIError: sqlalchemy_db_exception_handler,
    UniqueViolation: raw_psycopg_exception_handler,
    ExclusionViolation: raw_psycopg_exception_handler,
    RaiseException: raw_psycopg_exception_handler,
    CheckViolation: raw_psycopg_exception_handler,
    ForeignKeyViolation: raw_psycopg_exception_handler,
    RedisUnavailable: redis_unavailable_handler,
}


class DuplicateBookingSubmit(Exception):
    """Raised by the booking service on ux_bookings_no_duplicate_submit so the
    router can return the existing booking checkout payload (HTTP 409)."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.existing_booking_id = str(getattr(response, "booking_id", ""))
        super().__init__("duplicate booking submit")


STALE_BOOKING_DETAIL = "Booking state changed — refresh and retry."


class StaleBookingState(HTTPException):
    """Guarded UPDATE returned 0 rows — concurrent transition won (API_CONTRACTS)."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=STALE_BOOKING_DETAIL)
