-- Deployment gate: MUST run before the first booking (see spec/DATABASE.md).
-- Idempotent. Trigger 3 raises loudly if the 'accepted'/'offered'/'confirmed'
-- rows are missing. v2 adds the payment/dispatch lifecycle statuses:
-- payment_pending, abandoned, failed_no_pujari, disputed.
INSERT INTO status_types (domain, code, label) VALUES
    ('assignment', 'offered', 'Offered'),
    ('assignment', 'accepted', 'Accepted'),
    ('assignment', 'rejected', 'Rejected'),
    ('assignment', 'expired', 'Expired'),
    ('booking', 'payment_pending', 'Payment Pending'),
    ('booking', 'requested', 'Requested'),
    ('booking', 'confirmed', 'Confirmed'),
    ('booking', 'in_progress', 'In Progress'),
    ('booking', 'completed', 'Completed'),
    ('booking', 'cancelled', 'Cancelled'),
    ('booking', 'abandoned', 'Abandoned'),
    ('booking', 'failed_no_pujari', 'No Pujari Found'),
    ('booking', 'disputed', 'Disputed')
ON CONFLICT DO NOTHING;
