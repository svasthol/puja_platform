"""Shared SQL for TDS facilitation ledger net (positive reversal rows)."""

# Gross / taxable base net per FY (ledger gross_amount = taxable base on accrual).
LEDGER_GROSS_NET_EXPR = """
COALESCE(SUM(
    CASE
        WHEN l.entry_type IN ('accrual', 'catch_up') THEN l.gross_amount
        WHEN l.entry_type = 'reversal' THEN -l.gross_amount
        ELSE 0
    END
), 0)
"""

LEDGER_TDS_NET_EXPR = """
COALESCE(SUM(
    CASE
        WHEN l.entry_type IN ('accrual', 'catch_up') THEN l.tds_amount
        WHEN l.entry_type = 'reversal' THEN -l.tds_amount
        ELSE 0
    END
), 0)
"""

BOOKING_LEDGER_TDS_NET_EXPR = """
COALESCE(SUM(
    CASE
        WHEN entry_type IN ('accrual', 'catch_up') THEN tds_amount
        WHEN entry_type = 'reversal' THEN -tds_amount
        ELSE 0
    END
), 0)
"""
