"""Tests for derived panchangam muhurtam windows."""
from __future__ import annotations

from app.services.panchangam_muhurtam import (
    build_auspicious_windows,
    compute_amrita_ghadiya,
    compute_brahma_muhurtam,
)


def test_compute_brahma_muhurtam_hyderabad():
    out = compute_brahma_muhurtam("2026-08-05T05:57:38+05:30")
    assert out is not None
    assert out["start"] == "2026-08-05T04:21:38+05:30"
    assert out["end"] == "2026-08-05T05:09:38+05:30"


def test_compute_amrita_ghadiya_midday():
    out = compute_amrita_ghadiya(
        "2026-08-05T05:57:38+05:30",
        "2026-08-05T18:49:07+05:30",
    )
    assert out is not None
    # Solar noon ≈ 12:23; Abhijit ±24 min → 11:59–12:47
    assert "11:59" in out["start"]
    assert "12:47" in out["end"]


def test_build_auspicious_windows_adds_abhijit():
    windows = build_auspicious_windows(
        sunrise_iso="2026-08-05T05:57:38+05:30",
        sunset_iso="2026-08-05T18:49:07+05:30",
        locale="te",
        existing=[],
    )
    assert len(windows) == 1
    assert "అభిజిత" in windows[0]["label"]
