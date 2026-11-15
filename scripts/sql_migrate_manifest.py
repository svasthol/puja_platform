"""SSOT: ordered SQL migration runner steps under scripts/.

Every ``apply_migration_NNN.py`` (singular) and ``apply_migrations_*.py`` (chain)
must appear exactly once in the deploy sequence. CI gate G3 calls ``verify()`` so
new migration scripts cannot merge without being wired into ``migrate.sh``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SINGLE_RE = re.compile(r"^apply_migration_(\d{3})\.py$")
CHAIN_GLOB = "apply_migrations_*.py"


def _chain_covered_numbers(path: Path) -> frozenset[int]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"MIGRATION_NUMBERS\s*=\s*\(([^)]*)\)", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path.name}: MIGRATION_NUMBERS tuple not found")
    try:
        values = ast.literal_eval(f"({match.group(1)},)")
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"{path.name}: invalid MIGRATION_NUMBERS") from exc
    return frozenset(int(v) for v in values)


def discover_chain_scripts() -> list[tuple[int, str]]:
    """(first_migration_number, basename) sorted by first number."""
    chains: list[tuple[int, str]] = []
    for path in sorted(SCRIPTS_DIR.glob(CHAIN_GLOB)):
        nums = _chain_covered_numbers(path)
        if not nums:
            raise ValueError(f"{path.name}: empty MIGRATION_NUMBERS")
        chains.append((min(nums), path.name))
    chains.sort(key=lambda t: t[0])
    return chains


def discover_single_scripts() -> dict[int, str]:
    out: dict[int, str] = {}
    for path in SCRIPTS_DIR.iterdir():
        m = SINGLE_RE.match(path.name)
        if m:
            out[int(m.group(1))] = path.name
    return out


def numbers_covered_by_chains() -> frozenset[int]:
    covered: set[int] = set()
    for path in SCRIPTS_DIR.glob(CHAIN_GLOB):
        covered |= set(_chain_covered_numbers(path))
    return frozenset(covered)


def build_sql_migrate_steps() -> list[str]:
    """Ordered script basenames to run after ``alembic upgrade head`` (before grants)."""
    singles = discover_single_scripts()
    chains = discover_chain_scripts()
    covered = numbers_covered_by_chains()

    steps: list[str] = []
    chain_idx = 0
    for n in sorted(singles):
        while chain_idx < len(chains) and chains[chain_idx][0] < n:
            steps.append(chains[chain_idx][1])
            chain_idx += 1
        if n in covered:
            continue
        steps.append(singles[n])
    while chain_idx < len(chains):
        steps.append(chains[chain_idx][1])
        chain_idx += 1

    return steps


def verify() -> None:
    """Raise SystemExit on orphan migration scripts or duplicate coverage."""
    singles = discover_single_scripts()
    covered = numbers_covered_by_chains()
    steps = build_sql_migrate_steps()
    step_set = set(steps)

    for path in sorted(SCRIPTS_DIR.glob(CHAIN_GLOB)):
        if path.name not in step_set:
            raise SystemExit(
                f"G3 FAIL: chain script {path.name} not in migrate sequence "
                f"(fix scripts/sql_migrate_manifest.py or add chain)"
            )

    for n, name in sorted(singles.items()):
        if n in covered:
            raise SystemExit(
                f"G3 FAIL: {name} overlaps chain coverage {sorted(covered)}; "
                "remove duplicate single script or narrow the chain"
            )
        if name not in step_set:
            raise SystemExit(
                f"G3 FAIL: {name} exists on disk but is not in migrate sequence"
            )

    migrate_sh = SCRIPTS_DIR / "migrate.sh"
    text = migrate_sh.read_text(encoding="utf-8")
    if "run_sql_migrations.py" not in text:
        raise SystemExit(
            "G3 FAIL: migrate.sh must invoke scripts/run_sql_migrations.py "
            "(SSOT manifest)"
        )

    if len(steps) != len(step_set):
        raise SystemExit("G3 FAIL: duplicate entries in sql migrate steps")


def main() -> int:
    for step in build_sql_migrate_steps():
        print(step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())