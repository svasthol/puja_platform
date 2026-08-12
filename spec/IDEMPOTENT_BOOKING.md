# Idempotent booking create — duplicate submit handling (v3.1)

Production-grade double-tap protection for `POST /v1/bookings`, aligned with
Uber/Urban Company patterns: the same customer cannot hold two **active**
bookings for the same `(puja, scheduled_date, scheduled_time)`, and retries
must return the existing checkout session — never HTTP 500.

## Problem (bug fixed)

When `ux_bookings_no_duplicate_submit` fired on `db.flush()`:

1. PostgreSQL aborted the whole transaction.
2. The `except` block read `hold.slot_date` / `hold.slot_time` from an ORM
   object whose attributes were expired by the failed flush.
3. SQLAlchemy tried a lazy SELECT on the dead transaction →
   `InvalidRequestError: Can't operate on closed transaction` → **500**.

The duplicate itself was **correct**; only the handler was broken.

## Guarantees

| Layer | Mechanism |
|---|---|
| Database | Partial unique index `ux_bookings_no_duplicate_submit` on `(user_id, puja_id, scheduled_date, scheduled_time) WHERE cancelled_at IS NULL` |
| App — insert | `INSERT … ON CONFLICT DO NOTHING` on partial unique index (no aborted txn); SAVEPOINT used elsewhere (e.g. webhook paid_at flip) |
| App — lookup | Query existing row using **snapshot locals** (`slot_date`, `slot_time`, `puja_id`), never `hold.*` after a failed write |
| App — response | `DuplicateBookingSubmit` → router returns **409** with full checkout payload + `"idempotent": true` |
| Persistence | `bookings.razorpay_order_id` (migration 004) — resume Razorpay on double-tap |

## HTTP contract

### 201 Created — first submit

```json
{
  "booking_id": "uuid",
  "razorpay_order_id": "order_…",
  "amount_due_online": "2100.00",
  "amount_due_offline": "0.00",
  "total_amount": "2100.00",
  "platform_fee_gross": "21.00",
  "total_charged_online": "2121.00",
  "tax_statutory_config_id": "uuid",
  "tax_commercial_config_id": "uuid",
  "payment_mode": "full_online",
  "hold_expires_at": "2026-08-07T10:45:00Z",
  "idempotent": false
}
```

### 409 Conflict — duplicate active booking (idempotent)

Same shape as 201, with `"idempotent": true`. **Must return the same `platform_fee_gross` and
`tax_*_config_id` values as the original 201** — replays snapshot, does not recompute.

- If `payment_pending`: reopen Razorpay with `razorpay_order_id`.
- If `confirmed` / later: navigate to `GET /v1/bookings/{id}` (no new checkout).

`razorpay_order_id` may be `null` only for rows created before migration 004.

## Implementation map

| File | Responsibility |
|---|---|
| `app/services/booking_service.py` | `ON CONFLICT DO NOTHING` insert, `_lookup_duplicate_response`, persist `razorpay_order_id` |
| `app/api/v1/endpoints/bookings.py` | Catch `DuplicateBookingSubmit` → 409 |
| `app/core/exceptions.py` | `DuplicateBookingSubmit` carries `BookingCreateResponse` |
| `app/models/booking.py` | `razorpay_order_id` column |
| `migrations/versions/004_razorpay_order_id.py` | Alembic wrapper |
| `spec/db/migration_004.sql` | DDL source of truth |

## Test / dev scripts

`scripts/manual_verify_session.py` randomizes slot date/time each run
(`days=14..90`, hour `8..17`, minute `0|30`) so repeat manual sessions do not
collide with prior active bookings.

`scripts/dev_booking_flow_e2e.py` already randomizes slots.

## When duplicate is expected (not a bug)

- Customer double-taps "Pay" within seconds.
- Repeat E2E script with the same slot while a prior booking is still active
  (`cancelled_at IS NULL`).
- Confirmed booking for `2026-08-07 10:30` blocks a second create for that slot
  until cancelled, completed, or abandoned (sweep sets `cancelled_at`).

## Related spec

- `API_CONTRACTS.md` — error table + `POST /v1/bookings` body
- `DISPATCH_FLOW.md` — lifecycle step 2, race matrix row "Customer double-taps"
- `DATABASE.md` — migration 004 DDL, do-not-break list
