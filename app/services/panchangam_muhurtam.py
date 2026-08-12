"""Derived muhurtam windows from sunrise/sunset (§23.6 home ribbon)."""
from __future__ import annotations

import datetime as dt


def _parse_iso(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso)


def _iso(dt_val: dt.datetime) -> str:
    return dt_val.isoformat(timespec="seconds")


def compute_brahma_muhurtam(sunrise_iso: str) -> dict[str, str] | None:
    """48-minute window ending 48 minutes before local sunrise."""
    if not sunrise_iso.strip():
        return None
    sunrise = _parse_iso(sunrise_iso)
    start = sunrise - dt.timedelta(minutes=96)
    end = sunrise - dt.timedelta(minutes=48)
    return {"start": _iso(start), "end": _iso(end)}


def compute_amrita_ghadiya(sunrise_iso: str, sunset_iso: str) -> dict[str, str] | None:
    """Abhijit muhurtam — 48-minute midday window (±24 min from solar noon)."""
    if not sunrise_iso.strip() or not sunset_iso.strip():
        return None
    sunrise = _parse_iso(sunrise_iso)
    sunset = _parse_iso(sunset_iso)
    midpoint = sunrise + (sunset - sunrise) / 2
    start = midpoint - dt.timedelta(minutes=24)
    end = midpoint + dt.timedelta(minutes=24)
    return {"start": _iso(start), "end": _iso(end)}


def auspicious_window_label(locale: str) -> str:
    if locale == "te":
        return "అభిజిత ముహూర్తం"
    return "Abhijit Muhurtam"


def build_auspicious_windows(
    *,
    sunrise_iso: str,
    sunset_iso: str,
    locale: str,
    existing: list | None,
) -> list[dict[str, str]]:
    """Ensure at least one auspicious midday window for the ribbon."""
    out: list[dict[str, str]] = []
    if existing:
        for item in existing:
            if isinstance(item, dict) and item.get("start") and item.get("end"):
                out.append(
                    {
                        "label": str(item.get("label") or auspicious_window_label(locale)),
                        "start": str(item["start"]),
                        "end": str(item["end"]),
                    }
                )
    amrita = compute_amrita_ghadiya(sunrise_iso, sunset_iso)
    if amrita and not any(
        w.get("start") == amrita["start"] and w.get("end") == amrita["end"] for w in out
    ):
        out.insert(
            0,
            {
                "label": auspicious_window_label(locale),
                "start": amrita["start"],
                "end": amrita["end"],
            },
        )
    return out
