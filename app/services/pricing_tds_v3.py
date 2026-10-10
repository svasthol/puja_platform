"""TDS v3 facilitation math — SSOT: spec/plans/TDS_V3_IMPLEMENTATION.md."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.services.pricing import (
    ALLOWED_ENTITY_TYPES,
    TdsFacilitationConfig,
    default_tds_facilitation_config,
    use_no_pan_tds_rate,
)

CrossingBase = Literal["excess_slice", "full"]
_PAISE = Decimal("0.01")


@dataclass(frozen=True)
class FacilitationAccrualResult:
    """Rate applies to taxable_base (ledger gross_amount), not necessarily full booking value."""

    rate: Decimal
    tds_amount: Decimal
    taxable_base: Decimal
    turnover_increment: Decimal
    fy_gross_after: Decimal
    deduction_latched_after: bool


@dataclass(frozen=True)
class FacilitationReversalSlice:
    turnover_reversal: Decimal
    taxable_base_reversal: Decimal
    tds_reversal: Decimal


@dataclass(frozen=True)
class OnlineChargeBreakdown:
    booking_fee_inr: Decimal
    tds_collected_online_inr: Decimal
    razorpay_online_inr: Decimal
    amount_due_offline_inr: Decimal
    tds_rate_applied: Decimal


def _q2(value: Decimal) -> Decimal:
    return value.quantize(_PAISE)


def _crossing_base(cfg: TdsFacilitationConfig) -> CrossingBase:
    base = getattr(cfg, "tds_crossing_base", "excess_slice")
    return "full" if base == "full" else "excess_slice"


def taxable_facilitation_base(
    *,
    entity_type: str,
    fy_gross_before: Decimal,
    this_amount: Decimal,
    deduction_latched: bool,
    config: TdsFacilitationConfig,
) -> Decimal:
    """Taxable slice for TDS (ledger gross_amount), not FY turnover."""
    cfg = config
    amount = _q2(this_amount)
    fy_before = _q2(fy_gross_before)
    threshold = cfg.individual_fy_threshold_inr
    fy_after = fy_before + amount

    if entity_type in cfg.always_taxed_entity_types:
        return amount

    if fy_after <= threshold:
        return Decimal("0")

    if deduction_latched or fy_before >= threshold:
        return amount

    if _crossing_base(cfg) == "full":
        return amount
    return _q2(min(amount, fy_after - threshold))


def compute_facilitation_accrual(
    *,
    entity_type: str | None,
    pan_on_file: bool,
    fy_gross_before: Decimal,
    this_amount: Decimal,
    deduction_latched: bool = False,
    config: TdsFacilitationConfig | None = None,
    pan_status: str | None = None,
) -> FacilitationAccrualResult:
    """v3 accrual: threshold-first; excess_slice on crossing; turnover = full booking amount."""
    cfg = config or default_tds_facilitation_config()
    if entity_type is None or entity_type not in ALLOWED_ENTITY_TYPES:
        raise ValueError("entity_type required and must be confirmed before TDS accrual")

    amount = _q2(this_amount)
    fy_before = _q2(fy_gross_before)
    threshold = cfg.individual_fy_threshold_inr
    fy_after = fy_before + amount
    latched_after = deduction_latched or fy_after > threshold

    if entity_type in cfg.always_taxed_entity_types:
        rate = (
            cfg.no_pan_rate
            if use_no_pan_tds_rate(pan_on_file, pan_status)
            else cfg.pan_entity_rate
        )
        taxable = amount
        tds = _q2(taxable * rate)
        return FacilitationAccrualResult(
            rate=rate,
            tds_amount=tds,
            taxable_base=taxable,
            turnover_increment=amount,
            fy_gross_after=fy_after,
            deduction_latched_after=latched_after,
        )

    if fy_after <= threshold:
        return FacilitationAccrualResult(
            rate=Decimal("0"),
            tds_amount=Decimal("0"),
            taxable_base=Decimal("0"),
            turnover_increment=amount,
            fy_gross_after=fy_after,
            deduction_latched_after=False,
        )

    rate = (
        cfg.no_pan_rate
        if use_no_pan_tds_rate(pan_on_file, pan_status)
        else cfg.pan_entity_rate
    )
    taxable = taxable_facilitation_base(
        entity_type=entity_type,
        fy_gross_before=fy_before,
        this_amount=amount,
        deduction_latched=deduction_latched,
        config=cfg,
    )
    tds = _q2(taxable * rate)
    return FacilitationAccrualResult(
        rate=rate,
        tds_amount=tds,
        taxable_base=taxable,
        turnover_increment=amount,
        fy_gross_after=fy_after,
        deduction_latched_after=latched_after,
    )


def tds_on_facilitation_v3(
    entity_type: str | None,
    pan_on_file: bool,
    fy_gross_before: Decimal,
    this_amount: Decimal,
    *,
    deduction_latched: bool = False,
    config: TdsFacilitationConfig | None = None,
    pan_status: str | None = None,
) -> tuple[Decimal, Decimal]:
    """Backward-compatible (rate, tds_amount) for callers not yet on full result struct."""
    result = compute_facilitation_accrual(
        entity_type=entity_type,
        pan_on_file=pan_on_file,
        fy_gross_before=fy_gross_before,
        this_amount=this_amount,
        deduction_latched=deduction_latched,
        config=config,
        pan_status=pan_status,
    )
    return result.rate, result.tds_amount


def charge_breakdown(
    *,
    total_amount: Decimal,
    booking_fee: Decimal,
    tds_amount: Decimal,
    tds_rate: Decimal,
) -> OnlineChargeBreakdown:
    """T6 — Razorpay = booking fee + TDS; pujari offline = total − TDS."""
    total = _q2(total_amount)
    fee = _q2(booking_fee)
    tds = _q2(tds_amount)
    if tds > total:
        raise ValueError("tds_amount cannot exceed total_amount")
    return OnlineChargeBreakdown(
        booking_fee_inr=fee,
        tds_collected_online_inr=tds,
        razorpay_online_inr=_q2(fee + tds),
        amount_due_offline_inr=_q2(total - tds),
        tds_rate_applied=tds_rate,
    )


def reverse_facilitation(
    *,
    booking_turnover: Decimal,
    ledger_taxable_base: Decimal,
    ledger_tds_amount: Decimal,
    refund_fraction: Decimal,
) -> FacilitationReversalSlice:
    """T7 — proportional contra; refund_fraction in (0, 1] (e.g. 0.5 = 50% refund)."""
    if refund_fraction <= 0 or refund_fraction > 1:
        raise ValueError("refund_fraction must be in (0, 1]")
    frac = refund_fraction.quantize(Decimal("0.0001"))
    return FacilitationReversalSlice(
        turnover_reversal=_q2(booking_turnover * frac),
        taxable_base_reversal=_q2(ledger_taxable_base * frac),
        tds_reversal=_q2(ledger_tds_amount * frac),
    )


def deposit_round_inr(challan_total_paise: Decimal) -> Decimal:
    """s.288B at deposit — nearest ₹10 on challan aggregate (not per accrual row)."""
    rupees = _q2(challan_total_paise)
    return (rupees / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("10")
