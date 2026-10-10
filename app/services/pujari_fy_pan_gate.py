"""FY facilitation PAN warn (₹4.5L) and block (₹5L without PAN) — see spec/plans/PAN_FY_GATES.md."""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException, status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.pricing import TdsFacilitationConfig, load_tds_facilitation_config
from app.services.tds_accrual_service import fy_start_for_date

FyPanGateLevel = Literal["ok", "warn", "block"]

FY_PAN_GATE_BLOCKED = "FY_PAN_GATE_BLOCKED"
FY_PAN_GATE_WARN = "FY_PAN_GATE_WARN"

_BLOCK_MSG = (
    "PAN is required on your profile once FY facilitation reaches ₹5 lakh. "
    "Add PAN and entity type before going online, accepting offers, or recording collections."
)
_WARN_NO_PAN = (
    "You are approaching ₹5 lakh FY facilitation. Add and verify PAN on your profile "
    "so TDS uses the ₹5 lakh threshold (0.1% on amounts above it, not 5% on all collections)."
)
_WARN_WITH_PAN = (
    "You are approaching ₹5 lakh FY facilitation — after the threshold, TDS applies at "
    "0.1% on the facilitation amount above ₹5 lakh (with operative PAN)."
)


@dataclass(frozen=True)
class FyPanGateStatus:
    level: FyPanGateLevel
    message: str
    fy_gross_inr: Decimal
    warn_threshold_inr: Decimal
    block_threshold_inr: Decimal
    pan_on_file: bool
    entity_type: str | None
    requires_pan_before_continue: bool

    def to_tax_summary_fields(self) -> dict[str, Any]:
        return {
            "individual_fy_pan_warn_inr": str(self.warn_threshold_inr.quantize(Decimal("0.01"))),
            "fy_pan_gate_level": self.level,
            "fy_pan_gate_message": self.message,
            "requires_pan_before_continue": self.requires_pan_before_continue,
        }


async def current_fy_facilitation_gross(
    db: AsyncSession, *, pujari_id: uuid.UUID, fy_start: dt.date | None = None
) -> Decimal:
    """Sum total_amount for balance-collected bookings in the Indian FY (TDS-aligned base)."""
    anchor = fy_start or fy_start_for_date(dt.date.today())
    fy_end = dt.date(anchor.year + 1, 4, 1)
    gross = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(b.total_amount), 0) AS gross
                FROM bookings b
                WHERE b.pujari_id = :pid
                  AND b.balance_collected_at IS NOT NULL
                  AND b.balance_collected_at >= :fy_start
                  AND b.balance_collected_at < :fy_end
                """
            ),
            {"pid": str(pujari_id), "fy_start": anchor, "fy_end": fy_end},
        )
    ).scalar_one()
    return Decimal(str(gross)).quantize(Decimal("0.01"))


def evaluate_fy_pan_gate(
    *,
    fy_gross_inr: Decimal,
    pan_on_file: bool,
    entity_type: str | None,
    cfg: TdsFacilitationConfig,
    additional_collection_inr: Decimal = Decimal("0"),
) -> FyPanGateStatus:
    """Pure evaluation for tests and API."""
    warn_at = cfg.individual_fy_pan_warn_inr
    block_at = cfg.individual_fy_threshold_inr
    gross = fy_gross_inr.quantize(Decimal("0.01"))
    projected = (gross + additional_collection_inr.quantize(Decimal("0.01"))).quantize(
        Decimal("0.01")
    )

    if not pan_on_file and (gross >= block_at or projected >= block_at):
        return FyPanGateStatus(
            level="block",
            message=_BLOCK_MSG,
            fy_gross_inr=gross,
            warn_threshold_inr=warn_at,
            block_threshold_inr=block_at,
            pan_on_file=False,
            entity_type=entity_type,
            requires_pan_before_continue=True,
        )

    in_warn_band = gross >= warn_at and gross < block_at
    if in_warn_band:
        msg = _WARN_NO_PAN if not pan_on_file else _WARN_WITH_PAN
        return FyPanGateStatus(
            level="warn",
            message=msg,
            fy_gross_inr=gross,
            warn_threshold_inr=warn_at,
            block_threshold_inr=block_at,
            pan_on_file=pan_on_file,
            entity_type=entity_type,
            requires_pan_before_continue=False,
        )

    return FyPanGateStatus(
        level="ok",
        message="Within FY facilitation runway.",
        fy_gross_inr=gross,
        warn_threshold_inr=warn_at,
        block_threshold_inr=block_at,
        pan_on_file=pan_on_file,
        entity_type=entity_type,
        requires_pan_before_continue=False,
    )


async def fy_pan_gate_status_for_pujari(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    additional_collection_inr: Decimal = Decimal("0"),
) -> FyPanGateStatus:
    cfg = await load_tds_facilitation_config(db)
    row = (
        await db.execute(
            text(
                """
                SELECT (pan_status = 'operative') AS pan_on_file, entity_type
                FROM pujaris WHERE id = :pid
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Pujari not found.")
    gross = await current_fy_facilitation_gross(db, pujari_id=pujari_id)
    return evaluate_fy_pan_gate(
        fy_gross_inr=gross,
        pan_on_file=bool(row["pan_on_file"]),
        entity_type=row["entity_type"],
        cfg=cfg,
        additional_collection_inr=additional_collection_inr,
    )


async def assert_fy_pan_gate_allowed(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    additional_collection_inr: Decimal = Decimal("0"),
) -> None:
    """Raise 422 when PUJARI_FY_PAN_GATE_ENABLED and partner is in block tier."""
    if not get_settings().PUJARI_FY_PAN_GATE_ENABLED:
        return
    status = await fy_pan_gate_status_for_pujari(
        db, pujari_id=pujari_id, additional_collection_inr=additional_collection_inr
    )
    if status.level == "block":
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=fy_pan_gate_blocked_detail(status),
        )


def fy_pan_gate_blocked_detail(status: FyPanGateStatus) -> dict[str, str]:
    return {"code": FY_PAN_GATE_BLOCKED, "message": status.message}


def fy_pan_gate_collection_warning(status: FyPanGateStatus) -> dict[str, str]:
    """Non-blocking warn on confirm-balance success (bilingual clients localize by code)."""
    return {"message_code": FY_PAN_GATE_WARN, "message": status.message}
