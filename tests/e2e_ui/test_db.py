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

def _has_column(conn, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table, column),
        )
        return cur.fetchone() is not None


def _bookings_has_column(conn, column: str) -> bool:
    return _has_column(conn, "bookings", column)


def _build_bookings_sql(has_booking_fee: bool, has_balance_collected_amount: bool) -> str:
    booking_fee_sel = (
        "b.booking_fee," if has_booking_fee else "NULL::numeric AS booking_fee,"
    )
    balance_collected_amount_sel = (
        "b.balance_collected_amount,"
        if has_balance_collected_amount
        else "NULL::numeric AS balance_collected_amount,"
    )
    return f"""
SELECT
  b.id::text AS booking_id,
  st.code AS status,
  u.phone AS customer_phone,
  puja.name AS puja_name,
  b.scheduled_date,
  b.scheduled_time,
  b.total_amount,
  b.amount_due_online,
  b.amount_due_offline,
  {booking_fee_sel}
  {balance_collected_amount_sel}
  b.payment_mode,
  b.paid_at,
  b.balance_collected_at,
  b.pujari_id::text AS pujari_id,
  b.razorpay_order_id,
  p.amount AS payment_amount,
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
      AND ast.domain = 'assignment'
      AND ast.code = 'offered'
      AND ba.responded_at IS NULL
      AND ba.expires_at > now()
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


BOOKINGS_SQL = _build_bookings_sql(False, False)


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
        has_fee = _bookings_has_column(conn, "booking_fee")
        has_bal = _bookings_has_column(conn, "balance_collected_amount")
        sql = _build_bookings_sql(has_fee, has_bal)
        with conn.cursor() as cur:
            cur.execute(sql, (lim,))
            rows = cur.fetchall()
    return [{k: _json_val(v) for k, v in row.items()} for row in rows]


def fetch_booking_by_id(booking_id: str) -> dict[str, Any] | None:
    """Return one booking row for Sprint 1 settlement inspection."""
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        has_fee = _bookings_has_column(conn, "booking_fee")
        has_bal = _bookings_has_column(conn, "balance_collected_amount")
        base = _build_bookings_sql(has_fee, has_bal)
        sql = base.replace(
            "ORDER BY b.created_at DESC\nLIMIT %s",
            "AND b.id = %s::uuid\nORDER BY b.created_at DESC\nLIMIT 1",
        )
        with conn.cursor() as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()
    if row is None:
        return None
    return {k: _json_val(v) for k, v in row.items()}


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


def _table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            LIMIT 1
            """,
            (table,),
        )
        return cur.fetchone() is not None


def fetch_pujari_compliance(pujari_id: str) -> dict[str, Any]:
    """Read-only pujari PAN/entity_type + FY gross for Sprint 2 E2E preview."""
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        has_pan = _has_column(conn, "pujaris", "pan_hash")
        pan_sel = (
            "p.pan_hash IS NOT NULL AS pan_on_file,"
            if has_pan
            else "false AS pan_on_file,"
        )
        entity_sel = (
            "p.entity_type,"
            if _has_column(conn, "pujaris", "entity_type")
            else "NULL::varchar AS entity_type,"
        )
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  p.id::text AS pujari_id,
                  {pan_sel}
                  {entity_sel}
                  u.phone AS partner_phone,
                  u.full_name AS partner_name
                FROM pujaris p
                JOIN users u ON u.id = p.user_id
                WHERE p.id = %s::uuid
                LIMIT 1
                """,
                (pujari_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"pujari_id": pujari_id, "found": False}

        fy_gross = Decimal("0")
        tds_accrued = Decimal("0")
        if _table_exists(conn, "pujari_tax_year"):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT gross_facilitation, tds_accrued
                    FROM pujari_tax_year
                    WHERE pujari_id = %s::uuid
                    ORDER BY fy_start DESC
                    LIMIT 1
                    """,
                    (pujari_id,),
                )
                fy_row = cur.fetchone()
                if fy_row:
                    fy_gross = Decimal(str(fy_row["gross_facilitation"]))
                    tds_accrued = Decimal(str(fy_row["tds_accrued"]))

    out = {k: _json_val(v) for k, v in row.items()}
    out["found"] = True
    out["fy_gross_facilitation"] = float(fy_gross)
    out["tds_accrued"] = float(tds_accrued)
    return out


def fetch_tds_facilitation_settings() -> dict[str, Any]:
    """Read platform_settings.tds_facilitation or return code defaults (no app import)."""
    load_dotenv(PROJECT_ROOT / ".env")
    defaults = {
        "no_pan_rate_pct": "5",
        "pan_entity_rate_pct": "0.1",
        "individual_fy_threshold_inr": "500000",
        "fy_turnover_warn_inr": "1800000",
        "fy_turnover_block_inr": "2000000",
        "always_taxed_entity_types": ["firm", "trust", "company", "aop", "other"],
    }
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return defaults

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value_json FROM platform_settings WHERE key = 'tds_facilitation'"
            )
            row = cur.fetchone()
    if not row or not row.get("value_json"):
        return defaults
    raw = row["value_json"]
    return {**defaults, **raw}


def fetch_fy_booking_fee_revenue() -> float:
    """G2 monitor query — SUM(booking_fee) where paid in current FY (IST)."""
    load_dotenv(PROJECT_ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return 0.0

    with psycopg.connect(_normalize_db_url(db_url), row_factory=dict_row) as conn:
        if not _bookings_has_column(conn, "booking_fee"):
            return 0.0
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(booking_fee), 0) AS fy_fee_revenue
                FROM bookings
                WHERE paid_at IS NOT NULL
                  AND paid_at >= date_trunc(
                      'year',
                      (now() AT TIME ZONE 'Asia/Kolkata')::date
                  )
                """
            )
            row = cur.fetchone()
    if not row:
        return 0.0
    return float(row["fy_fee_revenue"] or 0)


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
