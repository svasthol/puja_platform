"""Sync reference CSV time columns from recorded fixtures (one-off ops)."""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "spec" / "plans" / "panchangam_reference_hyderabad.csv"
FIXTURES = ROOT / "spec" / "fixtures" / "panchangam_hyderabad_jul2026.json"
_IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _hhmm(iso: str) -> str:
    parsed = dt.datetime.fromisoformat(iso)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_IST)
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def main() -> None:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))["dates"]
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    fieldnames = list(rows[0].keys())
    for row in rows:
        data = fixtures[row["date"]]
        rahu = data["rahukalam"]
        yama = data["yamagandam"]
        row["rahu_start"] = _hhmm(rahu["start"])
        row["rahu_end"] = _hhmm(rahu["end"])
        row["yama_start"] = _hhmm(yama["start"])
        row["yama_end"] = _hhmm(yama["end"])
        row["sunrise"] = _hhmm(data["sunrise"])
        row["sunset"] = _hhmm(data["sunset"])
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"synced times for {len(rows)} rows")


if __name__ == "__main__":
    main()
