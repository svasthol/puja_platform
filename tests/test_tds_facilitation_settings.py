"""Admin TDS facilitation settings — dynamic slabs from platform_settings."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.pricing import (
    default_tds_facilitation_config,
    parse_tds_facilitation_config,
    tds_on_facilitation,
)


def test_default_config_matches_launch_slabs():
    cfg = default_tds_facilitation_config()
    assert cfg.no_pan_rate_pct == Decimal("5")
    assert cfg.individual_fy_threshold_inr == Decimal("500000")
    assert cfg.individual_fy_pan_warn_inr == Decimal("450000")
    assert cfg.fy_turnover_warn_inr == Decimal("1800000")


def test_parse_merges_partial_json():
    cfg = parse_tds_facilitation_config({"individual_fy_threshold_inr": 600000})
    assert cfg.individual_fy_threshold_inr == Decimal("600000")
    assert cfg.no_pan_rate_pct == Decimal("5")


def test_tds_respects_custom_threshold():
    cfg = parse_tds_facilitation_config({"individual_fy_threshold_inr": 400000})
    rate, tds = tds_on_facilitation(
        entity_type="individual",
        pan_on_file=True,
        fy_gross_before=Decimal("390000"),
        this_amount=Decimal("20000"),
        config=cfg,
        pan_status="operative",
    )
    assert rate == Decimal("0.001")
    assert tds == Decimal("10.00")

