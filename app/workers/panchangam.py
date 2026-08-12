"""
Panchangam vendor fetch worker (§23.6).

Beat schedules daily refresh for configured cities. When PANCHANGAM_VENDOR_URL is
unset the task is a no-op — ops can seed rows manually until vendor integration
is wired.

Vendor adapter: self-hosted telugu-panchangam-app or compatible JSON (see
SPEC_AMENDMENTS §23.6 vendor mapping).
"""
from __future__ import annotations

import datetime as dt
import time
import zoneinfo

import httpx
import psycopg
import structlog

from app.core.config import get_settings
from app.services.panchangam_cities import resolve_city
from app.services.panchangam_muhurtam import (
    build_auspicious_windows,
    compute_amrita_ghadiya,
    compute_brahma_muhurtam,
)
from app.workers.celery_app import celery_app
from app.workers.sweep import get_connection

log = structlog.get_logger("panchangam")
settings = get_settings()
_TZ = zoneinfo.ZoneInfo(settings.PLATFORM_TIMEZONE)

PANCHANGAM_REFRESH_LOCK_KEY = "panchangam_refresh_lock"
PANCHANGAM_REFRESH_LOCK_TTL_SECONDS = 3500  # beat cadence 1h; release before next tick
_CACHE_HORIZON_DAYS = 7  # today through today + 7 inclusive
_VENDOR_FETCH_RETRIES = 3
_VENDOR_FETCH_BACKOFF_SECONDS = 0.5


def _locale_value(raw: object, locale: str) -> str | None:
    """Resolve bilingual vendor object or plain string to one locale."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, dict):
        for key in (locale, "te", "en"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _time_window(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    start = raw.get("start")
    end = raw.get("end")
    if start and end:
        return {"start": str(start), "end": str(end)}
    return None


def _ends_at(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    end = raw.get("endsAt") or raw.get("ends_at")
    if end:
        return str(end)
    return None


def _unwrap_vendor_root(raw: dict) -> dict:
    """telugu-panchangam-app wraps payload in { data: { ... } }."""
    inner = raw.get("data")
    if isinstance(inner, dict):
        return inner
    return raw


def _normalize_vendor_payload(raw: dict, *, locale: str) -> dict:
    """Map vendor JSON to panchangam_daily columns (§23.6)."""
    data = _unwrap_vendor_root(raw)
    tithi = _locale_value(
        data.get("tithi") or data.get("Tithi") or raw.get("tithi"),
        locale,
    )
    nakshatram = _locale_value(
        data.get("nakshatram")
        or data.get("nakshatra")
        or data.get("Nakshatra")
        or raw.get("nakshatram"),
        locale,
    )
    vaaram = _locale_value(
        data.get("vaaram") or data.get("vara") or data.get("day"),
        locale,
    )
    yoga = _locale_value(data.get("yoga") or data.get("Yoga") or raw.get("yoga"), locale)
    rahu_kalam = _time_window(
        data.get("rahu_kalam")
        or data.get("rahukalam")
        or raw.get("rahu_kalam")
    )
    yama_gandam = _time_window(
        data.get("yama_gandam")
        or data.get("yamagandam")
        or raw.get("yama_gandam")
    )
    sunrise = data.get("sunrise") or raw.get("sunrise")
    sunset = data.get("sunset") or raw.get("sunset")
    sunrise_s = str(sunrise) if sunrise else ""
    sunset_s = str(sunset) if sunset else ""
    tithi_raw = data.get("tithi") or data.get("Tithi") or raw.get("tithi")
    nakshatra_raw = (
        data.get("nakshatram")
        or data.get("nakshatra")
        or data.get("Nakshatra")
        or raw.get("nakshatram")
    )
    yoga_raw = data.get("yoga") or data.get("Yoga") or raw.get("yoga")
    brahma = _time_window(data.get("brahma_muhurtam") or raw.get("brahma_muhurtam"))
    if brahma is None and sunrise_s:
        brahma = compute_brahma_muhurtam(sunrise_s)
    amrita = _time_window(
        data.get("amrita_ghadiya") or raw.get("amrita_ghadiya")
    )
    if amrita is None and sunrise_s and sunset_s:
        amrita = compute_amrita_ghadiya(sunrise_s, sunset_s)
    auspicious = build_auspicious_windows(
        sunrise_iso=sunrise_s,
        sunset_iso=sunset_s,
        locale=locale,
        existing=data.get("auspicious_windows") or raw.get("auspicious_windows"),
    )
    return {
        "vaaram": vaaram or "",
        "tithi": tithi or "",
        "tithi_end": _ends_at(tithi_raw),
        "nakshatram": nakshatram or "",
        "nakshatra_end": _ends_at(nakshatra_raw),
        "yoga": yoga,
        "yoga_end": _ends_at(yoga_raw),
        "rahu_kalam": rahu_kalam,
        "yama_gandam": yama_gandam,
        "sunrise": sunrise_s,
        "sunset": sunset_s,
        "brahma_muhurtam": brahma,
        "amrita_ghadiya": amrita,
        "varjyam": _time_window(data.get("varjyam") or raw.get("varjyam")),
        "durmuhurtam": _time_window(data.get("durmuhurtam") or raw.get("durmuhurtam")),
        "auspicious_windows": auspicious,
        "disclaimer": data.get("disclaimer") or raw.get("disclaimer") or "",
    }


def _validate_home_ribbon_payload(payload: dict) -> bool:
    """Worker invariant for home-ribbon fields (API schema keeps yama_gandam nullable)."""
    for field in ("vaaram", "tithi", "nakshatram", "sunrise", "sunset"):
        if not payload.get(field):
            return False
    if not payload.get("rahu_kalam") or not payload.get("yama_gandam"):
        return False
    return True


def _upsert_row(
    cur,
    *,
    city: str,
    panchang_date: dt.date,
    locale: str,
    panchang_system: str,
    payload: dict,
    fetched_at: dt.datetime,
) -> None:
    if not _validate_home_ribbon_payload(payload):
        raise ValueError("vendor payload missing required home-ribbon fields")
    cur.execute(
        """
        INSERT INTO panchangam_daily (
            city, panchang_date, locale, panchang_system,
            vaaram, tithi, tithi_end, nakshatram, nakshatra_end, yoga, yoga_end,
            rahu_kalam, yama_gandam, sunrise, sunset,
            brahma_muhurtam, amrita_ghadiya,
            varjyam, durmuhurtam, auspicious_windows,
            disclaimer, fetched_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (city, panchang_date, locale, panchang_system) DO UPDATE
        SET vaaram = EXCLUDED.vaaram,
            tithi = EXCLUDED.tithi,
            tithi_end = EXCLUDED.tithi_end,
            nakshatram = EXCLUDED.nakshatram,
            nakshatra_end = EXCLUDED.nakshatra_end,
            yoga = EXCLUDED.yoga,
            yoga_end = EXCLUDED.yoga_end,
            rahu_kalam = EXCLUDED.rahu_kalam,
            yama_gandam = EXCLUDED.yama_gandam,
            sunrise = EXCLUDED.sunrise,
            sunset = EXCLUDED.sunset,
            brahma_muhurtam = EXCLUDED.brahma_muhurtam,
            amrita_ghadiya = EXCLUDED.amrita_ghadiya,
            varjyam = EXCLUDED.varjyam,
            durmuhurtam = EXCLUDED.durmuhurtam,
            auspicious_windows = EXCLUDED.auspicious_windows,
            disclaimer = EXCLUDED.disclaimer,
            fetched_at = EXCLUDED.fetched_at
        """,
        (
            city,
            panchang_date,
            locale,
            panchang_system,
            payload.get("vaaram") or None,
            payload["tithi"],
            payload.get("tithi_end"),
            payload["nakshatram"],
            payload.get("nakshatra_end"),
            payload.get("yoga"),
            payload.get("yoga_end"),
            psycopg.types.json.Json(payload.get("rahu_kalam"))
            if payload.get("rahu_kalam")
            else None,
            psycopg.types.json.Json(payload.get("yama_gandam"))
            if payload.get("yama_gandam")
            else None,
            payload.get("sunrise") or None,
            payload.get("sunset") or None,
            psycopg.types.json.Json(payload.get("brahma_muhurtam"))
            if payload.get("brahma_muhurtam")
            else None,
            psycopg.types.json.Json(payload.get("amrita_ghadiya"))
            if payload.get("amrita_ghadiya")
            else None,
            psycopg.types.json.Json(payload.get("varjyam"))
            if payload.get("varjyam")
            else None,
            psycopg.types.json.Json(payload.get("durmuhurtam"))
            if payload.get("durmuhurtam")
            else None,
            psycopg.types.json.Json(payload.get("auspicious_windows") or []),
            payload.get("disclaimer") or "",
            fetched_at,
        ),
    )


def _fetch_vendor_json(
    *,
    panchang_date: dt.date,
    lat: float,
    lng: float,
    tz: str,
    locale: str,
) -> dict | None:
    params = {
        "date": panchang_date.isoformat(),
        "lat": lat,
        "lng": lng,
        "tz": tz,
        "lang": locale,
    }
    headers = {}
    if settings.PANCHANGAM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.PANCHANGAM_API_KEY}"

    last_exc: Exception | None = None
    for attempt in range(_VENDOR_FETCH_RETRIES):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    settings.PANCHANGAM_VENDOR_URL,
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                raw = resp.json()
                if isinstance(raw, dict):
                    return raw
                return None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt + 1 < _VENDOR_FETCH_RETRIES:
                time.sleep(_VENDOR_FETCH_BACKOFF_SECONDS * (attempt + 1))
    log.warning(
        "panchangam_vendor_fetch_failed",
        date=panchang_date.isoformat(),
        lat=lat,
        lng=lng,
        error=str(last_exc),
    )
    return None


def fetch_and_cache_panchangam(
    conn: psycopg.Connection,
    *,
    city: str,
    panchang_date: dt.date,
    locale: str = "te",
    panchang_system: str = "drik",
) -> bool:
    """Fetch one city+date from vendor when configured; return True if cached."""
    if not settings.PANCHANGAM_VENDOR_URL:
        return False
    if panchang_system != "drik":
        log.info(
            "panchangam_vakya_skipped",
            city=city,
            date=panchang_date.isoformat(),
            system=panchang_system,
        )
        return False

    city_meta = resolve_city(city)
    if city_meta is None:
        log.warning("panchangam_city_unknown", city=city)
        return False

    raw = _fetch_vendor_json(
        panchang_date=panchang_date,
        lat=city_meta["lat"],
        lng=city_meta["lng"],
        tz=city_meta["tz"],
        locale=locale,
    )
    if raw is None:
        return False

    payload = _normalize_vendor_payload(raw, locale=locale)
    fetched_at = dt.datetime.now(dt.UTC)
    try:
        with conn.cursor() as cur:
            _upsert_row(
                cur,
                city=city_meta["display"],
                panchang_date=panchang_date,
                locale=locale,
                panchang_system=panchang_system,
                payload=payload,
                fetched_at=fetched_at,
            )
        conn.commit()
    except ValueError:
        log.warning(
            "panchangam_vendor_payload_invalid",
            city=city_meta["display"],
            date=panchang_date.isoformat(),
            locale=locale,
        )
        return False
    log.info(
        "panchangam_cached",
        city=city_meta["display"],
        date=panchang_date.isoformat(),
        locale=locale,
        system=panchang_system,
    )
    return True


def refresh_panchangam_cache(conn: psycopg.Connection) -> dict:
    """Backfill today through today + 7 days for configured cities (idempotent)."""
    if not settings.PANCHANGAM_VENDOR_URL:
        return {"skipped": True, "reason": "no_vendor_url", "fetched": 0}
    today = dt.datetime.now(_TZ).date()
    dates = [today + dt.timedelta(days=i) for i in range(_CACHE_HORIZON_DAYS + 1)]
    locales = ("te", "en")
    fetched = 0
    for city in settings.PANCHANGAM_DEFAULT_CITIES:
        for pdate in dates:
            for locale in locales:
                if fetch_and_cache_panchangam(
                    conn,
                    city=city.strip(),
                    panchang_date=pdate,
                    locale=locale,
                ):
                    fetched += 1
    return {"skipped": False, "fetched": fetched}


@celery_app.task(name="app.workers.panchangam.refresh_panchangam_cache_task")
def refresh_panchangam_cache_task() -> dict:
    import redis as redis_lib

    r = redis_lib.from_url(str(settings.REDIS_URL))
    if not r.set(
        PANCHANGAM_REFRESH_LOCK_KEY,
        "1",
        nx=True,
        ex=PANCHANGAM_REFRESH_LOCK_TTL_SECONDS,
    ):
        log.info("panchangam_refresh_skipped_locked")
        return {"skipped": "locked"}

    conn = get_connection()
    try:
        return refresh_panchangam_cache(conn)
    finally:
        conn.close()
        r.delete(PANCHANGAM_REFRESH_LOCK_KEY)
