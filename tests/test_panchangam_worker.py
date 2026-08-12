"""Panchangam vendor normalization and fetch wiring (§23.6)."""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

from app.workers.panchangam import (
    _normalize_vendor_payload,
    _validate_home_ribbon_payload,
    fetch_and_cache_panchangam,
)


def test_normalize_telugu_panchangam_app_payload_te():
    raw = {
        "data": {
            "vara": {"te": "సోమవారం", "en": "Monday"},
            "tithi": {
                "te": "పంచమి",
                "en": "Panchami",
                "endsAt": "2026-03-23T18:32:00+05:30",
            },
            "nakshatra": {
                "te": "కృత్తిక",
                "en": "Krittika",
                "endsAt": "2026-03-23T20:15:00+05:30",
            },
            "yoga": {
                "te": "సౌభాగ్య",
                "en": "Saubhagya",
                "endsAt": "2026-03-23T16:04:00+05:30",
            },
            "rahukalam": {
                "start": "2026-03-23T09:03:00+05:30",
                "end": "2026-03-23T10:35:00+05:30",
            },
            "yamagandam": {
                "start": "2026-03-23T13:09:00+05:30",
                "end": "2026-03-23T14:41:00+05:30",
            },
            "sunrise": "2026-03-23T06:32:00+05:30",
            "sunset": "2026-03-23T18:45:00+05:30",
        }
    }
    out = _normalize_vendor_payload(raw, locale="te")
    assert out["vaaram"] == "సోమవారం"
    assert out["tithi"] == "పంచమి"
    assert out["tithi_end"] == "2026-03-23T18:32:00+05:30"
    assert out["nakshatram"] == "కృత్తిక"
    assert out["nakshatra_end"] == "2026-03-23T20:15:00+05:30"
    assert out["yoga_end"] == "2026-03-23T16:04:00+05:30"
    assert out["rahu_kalam"]["start"].startswith("2026-03-23")
    assert out["yama_gandam"]["end"].startswith("2026-03-23")
    assert out["sunrise"] == "2026-03-23T06:32:00+05:30"
    assert out["sunset"] == "2026-03-23T18:45:00+05:30"
    assert out["brahma_muhurtam"] is not None
    assert out["amrita_ghadiya"] is not None
    assert out["auspicious_windows"]


def test_normalize_flat_vendor_payload_en():
    raw = {
        "vaaram": "Tuesday",
        "tithi": "Shashthi",
        "nakshatram": "Rohini",
        "sunrise": "2026-01-01T06:00:00+05:30",
        "sunset": "2026-01-01T18:00:00+05:30",
    }
    out = _normalize_vendor_payload(raw, locale="en")
    assert out["vaaram"] == "Tuesday"
    assert out["tithi"] == "Shashthi"
    assert out["nakshatram"] == "Rohini"


def test_validate_home_ribbon_payload_requires_yama_gandam():
    base = {
        "vaaram": "Monday",
        "tithi": "Pratipada",
        "nakshatram": "Ashwini",
        "sunrise": "06:00",
        "sunset": "18:00",
        "rahu_kalam": {"start": "09:00", "end": "10:30"},
        "yama_gandam": {"start": "13:00", "end": "14:30"},
    }
    assert _validate_home_ribbon_payload(base)
    missing_yama = dict(base)
    missing_yama.pop("yama_gandam")
    assert not _validate_home_ribbon_payload(missing_yama)


@patch("app.workers.panchangam.settings")
@patch("app.workers.panchangam._fetch_vendor_json")
def test_fetch_and_cache_uses_lat_lng_tz(mock_fetch, mock_settings):
    mock_settings.PANCHANGAM_VENDOR_URL = "http://127.0.0.1:3001/api/panchangam"
    mock_fetch.return_value = {
        "data": {
            "vara": {"te": "బుధవారం", "en": "Wednesday"},
            "tithi": {"te": "పాడ్యమి", "en": "Pratipada"},
            "nakshatra": {"te": "పుష్యమి", "en": "Pushya"},
            "rahukalam": {"start": "12:21", "end": "13:59"},
            "yamagandam": {"start": "07:28", "end": "09:06"},
            "sunrise": "2026-07-15T05:51:00+05:30",
            "sunset": "2026-07-15T18:52:00+05:30",
        }
    }
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    ok = fetch_and_cache_panchangam(
        conn,
        city="Hyderabad",
        panchang_date=dt.date(2026, 7, 15),
        locale="te",
    )
    assert ok
    mock_fetch.assert_called_once_with(
        panchang_date=dt.date(2026, 7, 15),
        lat=17.38500,
        lng=78.48600,
        tz="Asia/Kolkata",
        locale="te",
    )
    conn.commit.assert_called_once()
    insert_args = cur.execute.call_args[0][1]
    assert insert_args[0] == "Hyderabad"


@patch("app.workers.panchangam.settings")
def test_fetch_and_cache_unknown_city(mock_settings):
    mock_settings.PANCHANGAM_VENDOR_URL = "http://127.0.0.1:3001/api/panchangam"
    conn = MagicMock()
    ok = fetch_and_cache_panchangam(
        conn,
        city="Mumbai",
        panchang_date=dt.date(2026, 7, 15),
    )
    assert not ok
    conn.cursor.assert_not_called()
