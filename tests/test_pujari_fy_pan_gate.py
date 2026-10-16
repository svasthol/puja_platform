"""FY PAN gate evaluation and enforcement flag wiring."""
from __future__ import annotations

from decimal import Decimal

from app.services.pricing import default_tds_facilitation_config
from app.services.pujari_fy_pan_gate import evaluate_fy_pan_gate


def test_fy_pan_gate_ok_below_warn():
    cfg = default_tds_facilitation_config()
    s = evaluate_fy_pan_gate(
        fy_gross_inr=Decimal("400000"),
        pan_on_file=False,
        entity_type=None,
        cfg=cfg,
    )
    assert s.level == "ok"
    assert not s.requires_pan_before_continue


def test_fy_pan_gate_warn_no_pan_at_four_five():
    cfg = default_tds_facilitation_config()
    s = evaluate_fy_pan_gate(
        fy_gross_inr=Decimal("460000"),
        pan_on_file=False,
        entity_type="individual",
        cfg=cfg,
    )
    assert s.level == "warn"


def test_fy_pan_gate_block_no_pan_at_five_lakh():
    cfg = default_tds_facilitation_config()
    s = evaluate_fy_pan_gate(
        fy_gross_inr=Decimal("500000"),
        pan_on_file=False,
        entity_type="individual",
        cfg=cfg,
    )
    assert s.level == "block"
    assert s.requires_pan_before_continue


def test_fy_pan_gate_block_projected_collection():
    cfg = default_tds_facilitation_config()
    s = evaluate_fy_pan_gate(
        fy_gross_inr=Decimal("480000"),
        pan_on_file=False,
        entity_type="individual",
        cfg=cfg,
        additional_collection_inr=Decimal("30000"),
    )
    assert s.level == "block"


def test_fy_pan_gate_no_block_when_pan_on_file_at_five_lakh():
    cfg = default_tds_facilitation_config()
    s = evaluate_fy_pan_gate(
        fy_gross_inr=Decimal("520000"),
        pan_on_file=True,
        entity_type="individual",
        cfg=cfg,
    )
    assert s.level == "ok"
