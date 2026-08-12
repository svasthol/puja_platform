"""Server-cached panchangam read path (§23.6)."""
from __future__ import annotations

import datetime as dt
import zoneinfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.panchangam import (
    AuspiciousWindow,
    PanchangamResponse,
    PanchangamTimeWindow,
)
from app.services.panchangam_muhurtam import (
    build_auspicious_windows,
    compute_amrita_ghadiya,
    compute_brahma_muhurtam,
)

_TZ = zoneinfo.ZoneInfo(get_settings().PLATFORM_TIMEZONE)
_DEFAULT_DISCLAIMER = (
    "Panchangam data is indicative. Please verify important muhurats with your pujari."
)


def _time_window(raw: dict | None) -> PanchangamTimeWindow | None:
    if not raw or "start" not in raw or "end" not in raw:
        return None
    return PanchangamTimeWindow(start=str(raw["start"]), end=str(raw["end"]))


def _auspicious_windows(raw: list | None) -> list[AuspiciousWindow]:
    if not raw:
        return []
    out: list[AuspiciousWindow] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        start = item.get("start")
        end = item.get("end")
        if label and start and end:
            out.append(
                AuspiciousWindow(label=str(label), start=str(start), end=str(end))
            )
    return out


def today_ist() -> dt.date:
    return dt.datetime.now(_TZ).date()


async def fetch_panchangam(
    db: AsyncSession,
    *,
    city: str,
    panchang_date: dt.date,
    locale: str,
    panchang_system: str = "drik",
) -> PanchangamResponse | None:
    row = (
        await db.execute(
            text(
                """
                SELECT city, panchang_date, locale, panchang_system,
                       vaaram, tithi, tithi_end, nakshatram, nakshatra_end,
                       yoga, yoga_end,
                       rahu_kalam, yama_gandam, sunrise, sunset,
                       brahma_muhurtam, amrita_ghadiya,
                       varjyam, durmuhurtam, auspicious_windows,
                       disclaimer, fetched_at
                FROM panchangam_daily
                WHERE lower(city) = lower(:city)
                  AND panchang_date = :pdate
                  AND locale = :locale
                  AND panchang_system = :psys
                """
            ),
            {
                "city": city.strip(),
                "pdate": panchang_date,
                "locale": locale,
                "psys": panchang_system,
            },
        )
    ).mappings().first()
    if row is None:
        return None
    sunrise = row.get("sunrise") or ""
    sunset = row.get("sunset") or ""
    locale = row["locale"]
    brahma_raw = row.get("brahma_muhurtam") or compute_brahma_muhurtam(sunrise)
    amrita_raw = row.get("amrita_ghadiya") or compute_amrita_ghadiya(sunrise, sunset)
    windows_raw = build_auspicious_windows(
        sunrise_iso=sunrise,
        sunset_iso=sunset,
        locale=locale,
        existing=row.get("auspicious_windows"),
    )
    return PanchangamResponse(
        city=row["city"],
        date=row["panchang_date"],
        panchang_system=row["panchang_system"],
        locale=locale,
        vaaram=row.get("vaaram") or "",
        tithi=row["tithi"],
        tithi_end=row.get("tithi_end"),
        nakshatram=row["nakshatram"],
        nakshatra_end=row.get("nakshatra_end"),
        yoga=row.get("yoga"),
        yoga_end=row.get("yoga_end"),
        rahu_kalam=_time_window(row.get("rahu_kalam")),
        yama_gandam=_time_window(row.get("yama_gandam")),
        sunrise=sunrise,
        sunset=sunset,
        brahma_muhurtam=_time_window(brahma_raw),
        amrita_ghadiya=_time_window(amrita_raw),
        varjyam=_time_window(row.get("varjyam")),
        durmuhurtam=_time_window(row.get("durmuhurtam")),
        auspicious_windows=_auspicious_windows(windows_raw),
        fetched_at=row["fetched_at"],
        disclaimer=row.get("disclaimer") or _DEFAULT_DISCLAIMER,
    )
