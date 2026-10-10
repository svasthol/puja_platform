"""
Launch-lite pricing and refund helpers (Sprint 1 booking_fee model).

Single source of truth for checkout amounts and refundable platform caps.
"""
from __future__ import annotations

import datetime as dt
import zoneinfo
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.lookups import PlatformSetting

BOOKING_FEE_LABEL = "Muhurat & Slot Lock Token"
_LAUNCH_PAYMENT_MODE = "booking_fee"
ALLOWED_ENTITY_TYPES = frozenset(
    {"individual", "huf", "company", "firm", "trust", "aop", "other"}
)
_ALLOWED_ENTITY_TYPES = ALLOWED_ENTITY_TYPES
_settings = get_settings()


async def load_booking_fee(db: AsyncSession) -> Decimal:
    """Configured platform fee for new checkouts."""
    row = (
        await db.execute(
            select(PlatformSetting.value_json).where(PlatformSetting.key == "booking_fee")
        )
    ).scalar_one_or_none()
    if row and row.get("amount") is not None:
        return Decimal(str(row["amount"])).quantize(Decimal("0.01"))
    return Decimal(str(_settings.DEFAULT_BOOKING_FEE)).quantize(Decimal("0.01"))


def booking_fee_label_from_setting(value_json: dict | None) -> str:
    if value_json and value_json.get("label"):
        return str(value_json["label"])
    return BOOKING_FEE_LABEL


async def load_booking_fee_setting(
    db: AsyncSession,
) -> tuple[Decimal, str]:
    row = (
        await db.execute(
            select(PlatformSetting.value_json).where(PlatformSetting.key == "booking_fee")
        )
    ).scalar_one_or_none()
    if row is None:
        return (
            Decimal(str(_settings.DEFAULT_BOOKING_FEE)).quantize(Decimal("0.01")),
            BOOKING_FEE_LABEL,
        )
    fee = Decimal(str(row.get("amount", _settings.DEFAULT_BOOKING_FEE))).quantize(
        Decimal("0.01")
    )
    return fee, booking_fee_label_from_setting(row)


def compute_booking_fee_amounts(
    total_amount: Decimal,
    booking_fee: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Returns (total_amount, amount_due_online, amount_due_offline, booking_fee)."""
    total = total_amount.quantize(Decimal("0.01"))
    fee = booking_fee.quantize(Decimal("0.01"))
    return total, Decimal("0"), total, fee


def platform_charge_amount(
    *,
    payment_mode: str,
    booking_fee: Decimal,
    amount_due_online: Decimal,
) -> Decimal:
    """Razorpay capture/refund cap — booking_fee at launch, legacy modes unchanged."""
    if payment_mode == _LAUNCH_PAYMENT_MODE:
        return booking_fee.quantize(Decimal("0.01"))
    return amount_due_online.quantize(Decimal("0.01"))


def refundable_platform_amount(
    *,
    booking_fee: Decimal,
    amount_due_online: Decimal,
    payment_mode: str,
    status_code: str,
    reason: str,
    payment_captured: bool = True,
) -> Decimal:
    """Refund cap for platform-collected money only."""
    cap = platform_charge_amount(
        payment_mode=payment_mode,
        booking_fee=booking_fee,
        amount_due_online=amount_due_online,
    )
    if not payment_captured or cap <= 0:
        return Decimal("0")

    if reason in ("no_pujari", "platform_failure", "late_payment", "platform_terminate"):
        return cap
    if reason == "pujari_cancel_rebroadcast":
        return Decimal("0")
    if reason == "customer_cancel":
        if status_code in ("payment_pending", "requested"):
            return cap
        if status_code == "confirmed" and payment_mode != _LAUNCH_PAYMENT_MODE:
            return cap  # legacy policy handled by caller for confirmed
        return Decimal("0")
    return Decimal("0")


def customer_cancel_refund_amount(
    *,
    booking_fee: Decimal,
    amount_due_online: Decimal,
    payment_mode: str,
    status_code: str,
    policy_pct: int,
) -> Decimal:
    """Customer-initiated cancel refund (launch: 0% after confirmed for booking_fee)."""
    if status_code == "payment_pending":
        return Decimal("0")
    if status_code == "requested":
        return refundable_platform_amount(
            booking_fee=booking_fee,
            amount_due_online=amount_due_online,
            payment_mode=payment_mode,
            status_code=status_code,
            reason="customer_cancel",
        )
    if status_code == "confirmed":
        if payment_mode == _LAUNCH_PAYMENT_MODE:
            return Decimal("0")
        online = amount_due_online.quantize(Decimal("0.01"))
        return (online * Decimal(policy_pct) / Decimal(100)).quantize(Decimal("0.01"))
    return Decimal("0")


TDS_FACILITATION_SETTINGS_KEY = "tds_facilitation"
_DEFAULT_ALWAYS_TAXED_ENTITY_TYPES = frozenset(
    {"firm", "trust", "company", "aop", "other"}
)


@dataclass(frozen=True)
class TdsFacilitationConfig:
    """Admin-tunable TDS facilitation slabs (platform_settings.tds_facilitation)."""

    no_pan_rate_pct: Decimal
    pan_entity_rate_pct: Decimal
    individual_fy_threshold_inr: Decimal
    individual_fy_pan_warn_inr: Decimal
    fy_turnover_warn_inr: Decimal
    fy_turnover_block_inr: Decimal
    always_taxed_entity_types: frozenset[str]
    tds_crossing_base: str = "excess_slice"

    @property
    def no_pan_rate(self) -> Decimal:
        return (self.no_pan_rate_pct / Decimal("100")).quantize(Decimal("0.0001"))

    @property
    def pan_entity_rate(self) -> Decimal:
        return (self.pan_entity_rate_pct / Decimal("100")).quantize(Decimal("0.0001"))

    def to_json(self) -> dict[str, Any]:
        return {
            "no_pan_rate_pct": str(self.no_pan_rate_pct),
            "pan_entity_rate_pct": str(self.pan_entity_rate_pct),
            "individual_fy_threshold_inr": str(self.individual_fy_threshold_inr),
            "individual_fy_pan_warn_inr": str(self.individual_fy_pan_warn_inr),
            "fy_turnover_warn_inr": str(self.fy_turnover_warn_inr),
            "fy_turnover_block_inr": str(self.fy_turnover_block_inr),
            "always_taxed_entity_types": sorted(self.always_taxed_entity_types),
            "tds_crossing_base": self.tds_crossing_base,
        }


def default_tds_facilitation_config() -> TdsFacilitationConfig:
    return TdsFacilitationConfig(
        no_pan_rate_pct=Decimal("5"),
        pan_entity_rate_pct=Decimal("0.1"),
        individual_fy_threshold_inr=Decimal("500000"),
        individual_fy_pan_warn_inr=Decimal("450000"),
        fy_turnover_warn_inr=Decimal("1800000"),
        fy_turnover_block_inr=Decimal("2000000"),
        always_taxed_entity_types=_DEFAULT_ALWAYS_TAXED_ENTITY_TYPES,
        tds_crossing_base="excess_slice",
    )


def parse_tds_facilitation_config(value_json: dict | None) -> TdsFacilitationConfig:
    """Merge platform_settings JSON with code defaults (future tax slab changes)."""
    base = default_tds_facilitation_config()
    if not value_json:
        return base
    entity_types = value_json.get("always_taxed_entity_types")
    parsed_types = (
        frozenset(str(t) for t in entity_types)
        if isinstance(entity_types, list) and entity_types
        else base.always_taxed_entity_types
    )
    return TdsFacilitationConfig(
        no_pan_rate_pct=Decimal(str(value_json.get("no_pan_rate_pct", base.no_pan_rate_pct))),
        pan_entity_rate_pct=Decimal(
            str(value_json.get("pan_entity_rate_pct", base.pan_entity_rate_pct))
        ),
        individual_fy_threshold_inr=Decimal(
            str(
                value_json.get(
                    "individual_fy_threshold_inr", base.individual_fy_threshold_inr
                )
            )
        ),
        individual_fy_pan_warn_inr=Decimal(
            str(
                value_json.get(
                    "individual_fy_pan_warn_inr", base.individual_fy_pan_warn_inr
                )
            )
        ),
        fy_turnover_warn_inr=Decimal(
            str(value_json.get("fy_turnover_warn_inr", base.fy_turnover_warn_inr))
        ),
        fy_turnover_block_inr=Decimal(
            str(value_json.get("fy_turnover_block_inr", base.fy_turnover_block_inr))
        ),
        always_taxed_entity_types=parsed_types,
        tds_crossing_base=str(
            value_json.get("tds_crossing_base", base.tds_crossing_base)
        ),
    )


async def load_tds_facilitation_config(
    db: AsyncSession,
    *,
    as_of: dt.datetime | None = None,
) -> TdsFacilitationConfig:
    """Statutory rates from tax_statutory_config (R9); commercial turnover knobs from platform_settings.

    When ``as_of`` is set (R15), pick the row with greatest ``effective_from`` still on or before
    that instant (platform timezone date). Otherwise use the latest statutory row globally.
    """
    from sqlalchemy import text

    if as_of is not None:
        tz = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)
        as_of_date = as_of.astimezone(tz).date()
        statutory = (
            await db.execute(
                text(
                    """
                    SELECT tds_no_pan_rate_pct,
                           tds_pan_entity_rate_pct,
                           tds_individual_fy_threshold_inr,
                           tds_fy_turnover_warn_inr,
                           tds_fy_turnover_block_inr,
                           tds_always_taxed_entity_types,
                           tds_crossing_base
                    FROM tax_statutory_config
                    WHERE effective_from <= :as_of_date
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """
                ),
                {"as_of_date": as_of_date},
            )
        ).mappings().first()
    else:
        statutory = (
            await db.execute(
                text(
                    """
                    SELECT tds_no_pan_rate_pct,
                           tds_pan_entity_rate_pct,
                           tds_individual_fy_threshold_inr,
                           tds_fy_turnover_warn_inr,
                           tds_fy_turnover_block_inr,
                           tds_always_taxed_entity_types,
                           tds_crossing_base
                    FROM tax_statutory_config
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
    commercial = (
        await db.execute(
            select(PlatformSetting.value_json).where(
                PlatformSetting.key == TDS_FACILITATION_SETTINGS_KEY
            )
        )
    ).scalar_one_or_none()
    base = parse_tds_facilitation_config(commercial)
    if statutory is None:
        return base
    entity_types = statutory["tds_always_taxed_entity_types"]
    parsed_types = (
        frozenset(str(t) for t in entity_types)
        if isinstance(entity_types, list) and entity_types
        else base.always_taxed_entity_types
    )
    return TdsFacilitationConfig(
        no_pan_rate_pct=Decimal(str(statutory["tds_no_pan_rate_pct"])),
        pan_entity_rate_pct=Decimal(str(statutory["tds_pan_entity_rate_pct"])),
        individual_fy_threshold_inr=Decimal(str(statutory["tds_individual_fy_threshold_inr"])),
        individual_fy_pan_warn_inr=Decimal(str(base.individual_fy_pan_warn_inr)),
        fy_turnover_warn_inr=Decimal(str(base.fy_turnover_warn_inr)),
        fy_turnover_block_inr=Decimal(str(base.fy_turnover_block_inr)),
        always_taxed_entity_types=parsed_types,
        tds_crossing_base=str(
            statutory.get("tds_crossing_base") or base.tds_crossing_base
        ),
    )


def use_no_pan_tds_rate(pan_on_file: bool, pan_status: str | None) -> bool:
    """Above-threshold fail-safe (R10): unverified/inoperative/no-PAN → 5% rate (not below ₹5L band)."""
    if not pan_on_file:
        return True
    return pan_status != "operative"


def tds_on_facilitation(
    entity_type: str | None,
    pan_on_file: bool,
    fy_gross_before: Decimal,
    this_amount: Decimal,
    *,
    config: TdsFacilitationConfig | None = None,
    pan_status: str | None = None,
    deduction_latched: bool = False,
) -> tuple[Decimal, Decimal]:
    """TDS v3 — threshold-first; excess_slice on crossing (see pricing_tds_v3)."""
    from app.services.pricing_tds_v3 import tds_on_facilitation_v3

    return tds_on_facilitation_v3(
        entity_type,
        pan_on_file,
        fy_gross_before,
        this_amount,
        deduction_latched=deduction_latched,
        config=config,
        pan_status=pan_status,
    )


def fy_turnover_monitor(
    fy_fee_revenue: Decimal,
    *,
    config: TdsFacilitationConfig | None = None,
) -> dict[str, Any]:
    """G2 monitor — platform fee turnover thresholds (admin-tunable)."""
    cfg = config or default_tds_facilitation_config()
    revenue = fy_fee_revenue.quantize(Decimal("0.01"))
    if revenue >= cfg.fy_turnover_block_inr:
        level = "block"
        message = "Escalate — compulsory GST registration risk if agent reading wrong."
    elif revenue >= cfg.fy_turnover_warn_inr:
        level = "warn"
        message = "Warn — plan GST registration."
    else:
        level = "ok"
        message = "Within safe runway."
    return {
        "fy_fee_revenue_inr": str(revenue),
        "warn_threshold_inr": str(cfg.fy_turnover_warn_inr),
        "block_threshold_inr": str(cfg.fy_turnover_block_inr),
        "level": level,
        "message": message,
    }
