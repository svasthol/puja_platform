"""
TEST ONLY — read-only booking feed for the E2E Test ops dashboard.

Never import from app/. Uses DATABASE_URL from project .env via psycopg.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BOOKINGS_SQL = """
SELECT
  b.id::text AS booking_id,
  st.code AS status,
  u.phone AS customer_phone,
  puja.name AS puja_name,
  b.scheduled_date,
  b.scheduled_time,
  b.total_amount,
  b.amount_due_online,
  b.payment_mode,
  b.paid_at,
  b.razorpay_order_id,
  p.gateway_txn_id AS razorpay_payment_id,
  b.created_at,
  (
    SELECT COUNT(*)::int FROM booking_assignments ba WHERE ba.booking_id = b.id
  ) AS offers_sent,
  (
    SELECT COUNT(*)::int
    FROM booking_assignments ba
    JOIN status_types ast ON ast.id = ba.status_id
    WHERE ba.booking_id = b.id
      AND ast.code = 'offered'
      AND ba.responded_at IS NULL
  ) AS offers_live,
  assignee.full_name AS assigned_pujari_name,
  assignee.phone AS assigned_pujari_phone
FROM bookings b
JOIN status_types st ON st.id = b.status_id
JOIN users u ON u.id = b.user_id
JOIN pujas puja ON puja.id = b.puja_id
LEFT JOIN payments p ON p.booking_id = b.id AND p.status = 'success'
LEFT JOIN pujaris pjr ON pjr.id = b.pujari_id
LEFT JOIN users assignee ON assignee.id = pjr.user_id
ORDER BY b.created_at DESC
LIMIT %s
"""


def _normalize_db_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


def _json_val(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, UUID):
        return str(v)
    return v


def fetch_recent_bookings(*, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent bookings for the test ops dashboard (read-only)."""
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")

    lim = max(1, min(int(limit), 100))
    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(BOOKINGS_SQL, (lim,))
            rows = cur.fetchall()
    return [{k: _json_val(v) for k, v in row.items()} for row in rows]


USER_BY_PHONE_SQL = """
SELECT
  u.id::text AS user_id,
  u.full_name,
  u.phone,
  u.is_active,
  COALESCE(
    (
      SELECT json_agg(r.name ORDER BY r.name)
      FROM user_roles ur
      JOIN roles r ON r.id = ur.role_id
      WHERE ur.user_id = u.id
    ),
    '[]'::json
  ) AS roles,
  EXISTS (SELECT 1 FROM admin_credentials ac WHERE ac.user_id = u.id) AS has_credential,
  (
    SELECT ac.activated_at IS NOT NULL
    FROM admin_credentials ac
    WHERE ac.user_id = u.id
  ) AS credential_activated
FROM users u
WHERE u.phone = %s
LIMIT 1
"""


PUJARI_BY_PHONE_SQL = """
SELECT p.id::text AS pujari_id, u.phone, u.full_name
FROM pujaris p
JOIN users u ON u.id = p.user_id
WHERE u.phone = %s
LIMIT 1
"""


def fetch_pujari_by_phone(phone: str) -> dict[str, Any] | None:
    """Resolve partner phone → pujari_id for E2E NO-DIRECT slot-hold test."""
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(PUJARI_BY_PHONE_SQL, (phone.strip(),))
            row = cur.fetchone()
    if row is None:
        return None
    return {k: _json_val(v) for k, v in row.items()}


def fetch_user_by_phone(phone: str) -> dict[str, Any] | None:
    """Resolve phone → user_id + roles for the Admin E2E tab (read-only)."""
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(USER_BY_PHONE_SQL, (phone.strip(),))
            row = cur.fetchone()
    if row is None:
        return None
    return {k: _json_val(v) for k, v in row.items()}


def redispatch_booking(
    booking_id: str,
    *,
    partner_phone: str = "+910000000011",
    force_immediate: bool = True,
) -> dict:
    """TEST ONLY — set partner presence + run one broadcast dispatch round synchronously.

    force_immediate=True (default): sets dispatch_starts_at=now() so advance bookings
    can be exercised in E2E without waiting until T-4h.
    """
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import psycopg
    import redis as redis_lib
    from psycopg.rows import tuple_row

    from app.core.config import get_settings
    from app.workers.dispatch import _dispatch_round

    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    with psycopg.connect(_normalize_db_url(db_url), row_factory=tuple_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.id FROM pujaris p JOIN users u ON u.id = p.user_id WHERE u.phone = %s",
                (partner_phone,),
            )
            row = cur.fetchone()
            if row:
                r = redis_lib.from_url(str(get_settings().REDIS_URL))
                r.set(f"presence:{row[0]}", "1", ex=120)
            if force_immediate:
                cur.execute(
                    """
                    INSERT INTO booking_dispatch_state (booking_id)
                    VALUES (%s::uuid)
                    ON CONFLICT (booking_id) DO NOTHING
                    """,
                    (booking_id,),
                )
                cur.execute(
                    """
                    UPDATE booking_dispatch_state
                    SET dispatch_starts_at = now(),
                        dispatch_deadline = GREATEST(
                            now() + interval '30 minutes',
                            COALESCE(dispatch_deadline, now() + interval '30 minutes')
                        )
                    WHERE booking_id = %s::uuid
                    """,
                    (booking_id,),
                )
                conn.commit()

    return _dispatch_round(booking_id, fresh=False)
