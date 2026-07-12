-- Migration 004 — persist Razorpay order id on bookings for idempotent checkout resume.
-- Applied after 003. Nullable: only payment_pending bookings have an order until paid/abandoned.
-- Partial unique: one Razorpay order maps to at most one booking (dedupe safety).

ALTER TABLE bookings ADD COLUMN razorpay_order_id VARCHAR(100);

CREATE UNIQUE INDEX ux_bookings_razorpay_order_id
    ON bookings (razorpay_order_id)
    WHERE razorpay_order_id IS NOT NULL;
