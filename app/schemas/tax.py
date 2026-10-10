"""Partner tax / TDS summary schemas (Sprint 2)."""
from __future__ import annotations

from pydantic import BaseModel


class PujariTaxSummary(BaseModel):
    fy_start: str
    fy_gross_facilitation: str
    tds_accrued: str
    individual_fy_threshold_inr: str
    individual_fy_pan_warn_inr: str
    threshold_remaining_inr: str
    pan_on_file: bool
    entity_type: str | None
    message: str
    fy_pan_gate_level: str
    fy_pan_gate_message: str
    requires_pan_before_continue: bool
