"""Validate panchangam engine against Venkatrama reference CSV (§23.6.1).

Usage:
    # Live engine on :3001 (default vendor URL from .env)
    python scripts/validate_panchangam_accuracy.py

    # CI / offline — compare recorded fixtures to reference CSV
    python scripts/validate_panchangam_accuracy.py --fixtures spec/fixtures/panchangam_hyderabad_jul2026.json

    # Re-record fixtures after engine upgrade (manual Venkatrama sign-off required)
    python scripts/validate_panchangam_accuracy.py --record-fixtures
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "spec" / "plans" / "panchangam_reference_hyderabad.csv"
DEFAULT_FIXTURES = ROOT / "spec" / "fixtures" / "panchangam_hyderabad_jul2026.json"

HYDERABAD_LAT = 17.385
HYDERABAD_LNG = 78.486
HYDERABAD_TZ = "Asia/Kolkata"

MAX_TRANSITION_MISMATCHES = 2
MIN_TIME_MATCHES = 27
RAHU_YAMA_TOLERANCE_MIN = 3
SUN_TOLERANCE_MIN = 2

VAARAM_TE_TO_NUM: dict[str, int] = {
    "ఆదివారం": 0,
    "సోమవారం": 1,
    "మంగళవారం": 2,
    "బుధవారం": 3,
    "గురువారం": 4,
    "శుక్రవారం": 5,
    "శనివారం": 6,
}


@dataclass
class ReferenceRow:
    date: str
    vaaram_te: str
    tithi_number: int
    nakshatra_number: int
    vara_number: int
    is_transition: bool
    rahu_start: str
    rahu_end: str
    yama_start: str
    yama_end: str
    sunrise: str
    sunset: str


@dataclass
class ActualRow:
    tithi_number: int
    nakshatra_number: int
    vara_number: int
    rahukalam_start: str
    rahukalam_end: str
    yamagandam_start: str
    yamagandam_end: str
    sunrise: str
    sunset: str


@dataclass
class ValidationReport:
    number_mismatches: list[str] = field(default_factory=list)
    transition_mismatches: list[str] = field(default_factory=list)
    non_transition_mismatches: list[str] = field(default_factory=list)
    time_failures: list[str] = field(default_factory=list)
    time_passes: int = 0

    @property
    def passed(self) -> bool:
        return (
            len(self.non_transition_mismatches) == 0
            and len(self.transition_mismatches) <= MAX_TRANSITION_MISMATCHES
            and self.time_passes >= MIN_TIME_MATCHES
        )


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "y", "yes", "true", "t"}


def load_reference_csv(path: Path) -> list[ReferenceRow]:
    rows: list[ReferenceRow] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            vara_num = int(raw["vara_number"]) if raw.get("vara_number") else VAARAM_TE_TO_NUM[
                raw["vaaram_te"].strip()
            ]
            rows.append(
                ReferenceRow(
                    date=raw["date"],
                    vaaram_te=raw["vaaram_te"],
                    tithi_number=int(raw["tithi_number"]),
                    nakshatra_number=int(raw["nakshatra_number"]),
                    vara_number=vara_num,
                    is_transition=_parse_bool(raw.get("is_transition", "")),
                    rahu_start=raw["rahu_start"],
                    rahu_end=raw["rahu_end"],
                    yama_start=raw["yama_start"],
                    yama_end=raw["yama_end"],
                    sunrise=raw["sunrise"],
                    sunset=raw["sunset"],
                )
            )
    return rows


def _extract_actual(data: dict) -> ActualRow:
    tithi = data.get("tithi") or {}
    nak = data.get("nakshatra") or data.get("nakshatram") or {}
    vara = data.get("vara") or data.get("vaaram") or {}
    rahu = data.get("rahukalam") or data.get("rahu_kalam") or {}
    yama = data.get("yamagandam") or data.get("yama_gandam") or {}
    return ActualRow(
        tithi_number=int(tithi["number"]),
        nakshatra_number=int(nak["number"]),
        vara_number=int(vara["number"]),
        rahukalam_start=str(rahu["start"]),
        rahukalam_end=str(rahu["end"]),
        yamagandam_start=str(yama["start"]),
        yamagandam_end=str(yama["end"]),
        sunrise=str(data["sunrise"]),
        sunset=str(data["sunset"]),
    )


def fetch_vendor(date: str, vendor_url: str) -> dict:
    resp = httpx.get(
        vendor_url,
        params={
            "date": date,
            "lat": HYDERABAD_LAT,
            "lng": HYDERABAD_LNG,
            "tz": HYDERABAD_TZ,
            "lang": "te",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"{date}: vendor response missing data object")
    return data


def load_fixtures(path: Path) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    dates = raw.get("dates")
    if not isinstance(dates, dict):
        raise ValueError("fixtures file must contain a dates object")
    return dates


def record_fixtures(
    references: list[ReferenceRow],
    vendor_url: str,
    out_path: Path,
) -> None:
    dates: dict[str, dict] = {}
    for ref in references:
        data = fetch_vendor(ref.date, vendor_url)
        dates[ref.date] = data
    payload = {
        "meta": {
            "city": "Hyderabad",
            "lat": HYDERABAD_LAT,
            "lng": HYDERABAD_LNG,
            "tz": HYDERABAD_TZ,
            "vendor_url": vendor_url,
            "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
            "reference_csv": str(DEFAULT_CSV.relative_to(ROOT)),
        },
        "dates": dates,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"recorded {len(dates)} dates → {out_path}")


def _csv_local_time(date: str, hhmm: str) -> dt.datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    day = dt.date.fromisoformat(date)
    return dt.datetime.combine(day, dt.time(hour, minute))


def _iso_local(iso: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(iso)
    if parsed.tzinfo is not None:
        return parsed.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).replace(
            tzinfo=None
        )
    return parsed


def _within_minutes(expected_hhmm: str, actual_iso: str, date: str, tolerance: int) -> bool:
    expected = _csv_local_time(date, expected_hhmm)
    actual = _iso_local(actual_iso)
    delta = abs((expected - actual).total_seconds()) / 60
    return delta <= tolerance


def times_match(ref: ReferenceRow, actual: ActualRow) -> bool:
    checks = [
        _within_minutes(ref.rahu_start, actual.rahukalam_start, ref.date, RAHU_YAMA_TOLERANCE_MIN),
        _within_minutes(ref.rahu_end, actual.rahukalam_end, ref.date, RAHU_YAMA_TOLERANCE_MIN),
        _within_minutes(ref.yama_start, actual.yamagandam_start, ref.date, RAHU_YAMA_TOLERANCE_MIN),
        _within_minutes(ref.yama_end, actual.yamagandam_end, ref.date, RAHU_YAMA_TOLERANCE_MIN),
        _within_minutes(ref.sunrise, actual.sunrise, ref.date, SUN_TOLERANCE_MIN),
        _within_minutes(ref.sunset, actual.sunset, ref.date, SUN_TOLERANCE_MIN),
    ]
    return all(checks)


def numbers_match(ref: ReferenceRow, actual: ActualRow) -> bool:
    return (
        ref.tithi_number == actual.tithi_number
        and ref.nakshatra_number == actual.nakshatra_number
        and ref.vara_number == actual.vara_number
    )


def validate(
    references: list[ReferenceRow],
    *,
    vendor_url: str | None = None,
    fixtures: dict[str, dict] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    for ref in references:
        if fixtures is not None:
            raw = fixtures.get(ref.date)
            if raw is None:
                report.number_mismatches.append(f"{ref.date}: missing fixture")
                continue
            data = raw
        else:
            assert vendor_url
            data = fetch_vendor(ref.date, vendor_url)

        actual = _extract_actual(data)
        if numbers_match(ref, actual):
            if times_match(ref, actual):
                report.time_passes += 1
            else:
                report.time_failures.append(ref.date)
            continue

        detail = (
            f"{ref.date}: expected tithi#{ref.tithi_number} nak#{ref.nakshatra_number} "
            f"vara#{ref.vara_number}, got tithi#{actual.tithi_number} "
            f"nak#{actual.nakshatra_number} vara#{actual.vara_number}"
        )
        report.number_mismatches.append(detail)
        if ref.is_transition:
            report.transition_mismatches.append(ref.date)
        else:
            report.non_transition_mismatches.append(ref.date)

    return report


def print_report(report: ValidationReport) -> None:
    print(f"non-transition mismatches: {len(report.non_transition_mismatches)} (max 0)")
    if report.non_transition_mismatches:
        for d in report.non_transition_mismatches:
            print(f"  - {d}")
    print(
        f"transition mismatches: {len(report.transition_mismatches)} "
        f"(max {MAX_TRANSITION_MISMATCHES})"
    )
    if report.transition_mismatches:
        for d in report.transition_mismatches:
            print(f"  - {d}")
    print(f"time passes: {report.time_passes}/30 (min {MIN_TIME_MATCHES})")
    if report.time_failures:
        print(f"time failures ({len(report.time_failures)}): {', '.join(report.time_failures)}")
    if report.number_mismatches:
        print("number mismatches:")
        for line in report.number_mismatches:
            print(f"  - {line}")
    print("RESULT:", "PASS" if report.passed else "FAIL")


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Panchangam accuracy gate (§23.6.1)")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--fixtures", type=Path, help="Use recorded vendor JSON instead of live HTTP")
    parser.add_argument(
        "--record-fixtures",
        action="store_true",
        help="Fetch live vendor and write fixtures file",
    )
    parser.add_argument(
        "--fixtures-out",
        type=Path,
        default=DEFAULT_FIXTURES,
        help="Output path for --record-fixtures",
    )
    args = parser.parse_args(argv)

    references = load_reference_csv(args.csv)
    vendor_url = os.environ.get(
        "PANCHANGAM_VENDOR_URL", "http://127.0.0.1:3001/api/panchangam"
    )

    if args.record_fixtures:
        record_fixtures(references, vendor_url, args.fixtures_out)
        return 0

    fixture_data = load_fixtures(args.fixtures) if args.fixtures else None
    report = validate(
        references,
        vendor_url=vendor_url if fixture_data is None else None,
        fixtures=fixture_data,
    )
    print_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
