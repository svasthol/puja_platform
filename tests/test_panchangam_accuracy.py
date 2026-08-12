"""CI: panchangam accuracy gate against recorded fixtures (§23.6.1)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_panchangam_accuracy import (  # noqa: E402
    load_fixtures,
    load_reference_csv,
    validate,
)


def test_panchangam_accuracy_fixtures_gate():
    fixtures_path = ROOT / "spec" / "fixtures" / "panchangam_hyderabad_jul2026.json"
    csv_path = ROOT / "spec" / "plans" / "panchangam_reference_hyderabad.csv"
    assert fixtures_path.is_file(), f"missing fixtures: {fixtures_path}"

    references = load_reference_csv(csv_path)
    report = validate(references, fixtures=load_fixtures(fixtures_path))
    assert report.passed, (
        f"accuracy gate failed: non_transition={report.non_transition_mismatches}, "
        f"transition={report.transition_mismatches}, time_passes={report.time_passes}"
    )
