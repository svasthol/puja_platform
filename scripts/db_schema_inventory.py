"""Export full schema inventory (every table's columns + constraints) for audit.

Usage:
  python scripts/db_schema_inventory.py --url "$DEV_DATABASE_URL" --out dev_schema.md
  python scripts/db_schema_inventory.py --url "$STAGING_DATABASE_URL" --format json --out staging.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from db_schema_catalog import fetch_catalog  # noqa: E402

_CONTYPE_ORDER = ("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK", "EXCLUDE")


def _constraints_by_table(catalog: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sig in catalog.get("constraints", []):
        table, kind, defn = sig.split("|", 2) if "|" in sig else (sig, "", "")
        out.setdefault(table, []).append(f"{kind}: {defn}")
    for table in out:
        out[table].sort()
    return out


def to_markdown(catalog: dict, label: str) -> str:
    lines = [
        f"# Schema inventory — {label}",
        f"",
        f"Database: `{catalog['database']}` · Alembic: `{catalog.get('alembic_version')}`",
        f"",
    ]
    for table in catalog.get("tables", []):
        lines.append(f"## `{table}`")
        lines.append("")
        lines.append("### Columns")
        lines.append("")
        lines.append("| # | Column | Type | Nullable | Default |")
        lines.append("|---|--------|------|----------|---------|")
        for col_sig in catalog.get("columns", {}).get(table, []):
            # bookings.id|uuid|null=NO|def=|ord=1
            segments = col_sig.split("|")
            col_name = segments[0].split(".", 1)[-1]
            udt = segments[1] if len(segments) > 1 else ""
            parts = dict(p.split("=", 1) for p in segments[2:] if "=" in p)
            lines.append(
                f"| {parts.get('ord', '')} | `{col_name}` | `{udt}` | "
                f"{parts.get('null', '')} | `{parts.get('def', '')}` |"
            )
        lines.append("")
        cbt = _constraints_by_table(catalog).get(table, [])
        if cbt:
            lines.append("### Constraints")
            lines.append("")
            for c in cbt:
                lines.append(f"- `{c}`")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export DB schema inventory")
    parser.add_argument("--url", required=True)
    parser.add_argument("--label", default="database")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    catalog = fetch_catalog(args.url)
    if args.format == "json":
        args.out.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    else:
        args.out.write_text(to_markdown(catalog, args.label), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
