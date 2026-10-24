"""Read-only Postgres catalog snapshot for dev/staging parity checks.

Normalizes public-schema objects for stable diffing (tables, columns, constraints,
indexes, triggers, extensions). No DDL; safe on production URLs with SELECT on catalogs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

SYSTEM_TABLES = frozenset({"spatial_ref_sys"})
_CONTYPE_LABEL = {"p": "PRIMARY KEY", "u": "UNIQUE", "f": "FOREIGN KEY", "c": "CHECK", "x": "EXCLUDE"}
_INTERNAL_NOT_NULL_NAME = re.compile(r"^\d+_\d+_not_null$")


def normalize_db_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
    )


def _column_key(row: tuple[Any, ...]) -> str:
    table, name, udt, nullable, default, pos = row
    default_s = _norm_default(default)
    return f"{table}.{name}|{udt}|null={nullable}|def={default_s}|ord={pos}"


def _norm_default(default: Any) -> str:
    if default is None:
        return ""
    s = str(default).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_sql_fragment(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _is_internal_not_null_check(conname: str, definition: str) -> bool:
    if _INTERNAL_NOT_NULL_NAME.match(conname):
        return True
    return bool(re.fullmatch(r".+ IS NOT NULL", definition.strip(), re.IGNORECASE))


def _constraint_signature(table: str, contype: str, definition: str) -> str:
    label = _CONTYPE_LABEL.get(contype, contype)
    return f"{table}|{label}|{_norm_sql_fragment(definition)}"


def _index_signature(table: str, indexdef: str) -> str:
    body = re.sub(
        r"^CREATE (UNIQUE )?INDEX \S+ ON (ONLY )?(public\.)?",
        "",
        indexdef.strip(),
        flags=re.IGNORECASE,
    )
    return f"{table}|{_norm_sql_fragment(body)}"


def fetch_catalog(url: str) -> dict[str, Any]:
    import psycopg

    sync = normalize_db_url(url)
    with psycopg.connect(sync) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr()::text, version()")
            db_name, server_host, pg_version = cur.fetchone()

            cur.execute(
                "SELECT extname, extversion FROM pg_extension ORDER BY 1"
            )
            extensions = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY 1
                """
            )
            tables = [r[0] for r in cur.fetchall() if r[0] not in SYSTEM_TABLES]

            cur.execute(
                """
                SELECT table_name, column_name, udt_name, is_nullable, column_default,
                       ordinal_position
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            columns: dict[str, list[str]] = {}
            for row in cur.fetchall():
                table = row[0]
                if table in SYSTEM_TABLES:
                    continue
                columns.setdefault(table, []).append(_column_key(row))

            cur.execute(
                """
                SELECT c.relname, con.conname, con.contype::text,
                       pg_get_constraintdef(con.oid, true)
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = con.connamespace
                WHERE n.nspname = 'public'
                  AND con.contype IN ('p', 'u', 'f', 'c', 'x')
                ORDER BY 1, 2
                """
            )
            constraints: list[str] = []
            for table, conname, contype, definition in cur.fetchall():
                if table in SYSTEM_TABLES:
                    continue
                if contype == "c" and _is_internal_not_null_check(conname, definition or ""):
                    continue
                constraints.append(_constraint_signature(table, contype, definition or ""))

            cur.execute(
                """
                SELECT tablename, indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY 1, 2
                """
            )
            indexes: list[str] = []
            for table, _iname, idef in cur.fetchall():
                if table in SYSTEM_TABLES:
                    continue
                indexes.append(_index_signature(table, idef))

            cur.execute(
                """
                SELECT c.relname AS table_name, t.tgname AS trigger_name
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND NOT t.tgisinternal
                ORDER BY 1, 2
                """
            )
            triggers = [f"{r[0]}.{r[1]}" for r in cur.fetchall()]

            cur.execute(
                """
                SELECT sequence_name, data_type, start_value, minimum_value,
                       maximum_value, increment
                FROM information_schema.sequences
                WHERE sequence_schema = 'public'
                ORDER BY 1
                """
            )
            sequences = [
                f"{r[0]}|{r[1]}|start={r[2]}|min={r[3]}|max={r[4]}|inc={r[5]}"
                for r in cur.fetchall()
            ]

            cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
            alembic_row = cur.fetchone()
            alembic_version = alembic_row[0] if alembic_row else None

    return {
        "database": db_name,
        "server_host": server_host,
        "pg_version_prefix": (pg_version or "")[:80],
        "extensions": extensions,
        "tables": tables,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "triggers": triggers,
        "sequences": sequences,
        "alembic_version": alembic_version,
    }


@dataclass
class SchemaDiff:
    only_left_tables: list[str]
    only_right_tables: list[str]
    column_diffs: list[str]
    constraint_diffs: list[str]
    index_diffs: list[str]
    trigger_diffs: list[str]
    sequence_diffs: list[str]
    extension_diffs: list[str]
    extension_warnings: list[str]
    alembic_mismatch: str | None

    @property
    def ok(self) -> bool:
        return not any(
            [
                self.only_left_tables,
                self.only_right_tables,
                self.column_diffs,
                self.constraint_diffs,
                self.index_diffs,
                self.trigger_diffs,
                self.sequence_diffs,
                self.extension_diffs,
                self.alembic_mismatch,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "only_left_tables": self.only_left_tables,
            "only_right_tables": self.only_right_tables,
            "column_diffs": self.column_diffs,
            "constraint_diffs": self.constraint_diffs,
            "index_diffs": self.index_diffs,
            "trigger_diffs": self.trigger_diffs,
            "sequence_diffs": self.sequence_diffs,
            "extension_diffs": self.extension_diffs,
            "extension_warnings": self.extension_warnings,
            "alembic_mismatch": self.alembic_mismatch,
        }


def diff_catalogs(
    left: dict[str, Any],
    right: dict[str, Any],
    left_label: str = "left",
    right_label: str = "right",
) -> SchemaDiff:
    left_tables = set(left["tables"])
    right_tables = set(right["tables"])
    only_left_tables = sorted(left_tables - right_tables)
    only_right_tables = sorted(right_tables - left_tables)

    column_diffs: list[str] = []
    for table in sorted(left_tables & right_tables):
        lc = left["columns"].get(table, [])
        rc = right["columns"].get(table, [])
        if lc == rc:
            continue
        only_l = sorted(set(lc) - set(rc))
        only_r = sorted(set(rc) - set(lc))
        if only_l or only_r:
            for col in only_l[:20]:
                column_diffs.append(f"{table}: ONLY {left_label}: {col}")
            for col in only_r[:20]:
                column_diffs.append(f"{table}: ONLY {right_label}: {col}")
            if len(only_l) + len(only_r) > 40:
                column_diffs.append(
                    f"{table}: ... {len(only_l) + len(only_r) - 40} more column diffs"
                )
        else:
            column_diffs.append(
                f"{table}: column order/type mismatch ({left_label}={len(lc)}, "
                f"{right_label}={len(rc)} cols)"
            )

    ext_diffs: list[str] = []
    ext_warnings: list[str] = []
    le, re = left.get("extensions", {}), right.get("extensions", {})
    for name in sorted(set(le) | set(re)):
        lv, rv = le.get(name), re.get(name)
        if lv is None:
            ext_diffs.append(f"extension missing on {left_label}: {name}")
        elif rv is None:
            ext_diffs.append(f"extension missing on {right_label}: {name}")
        elif lv != rv:
            ext_warnings.append(
                f"extension {name}: {left_label}={lv} {right_label}={rv} "
                f"(version differs by OS image; not a schema drift)"
            )

    alembic_mismatch = None
    la, ra = left.get("alembic_version"), right.get("alembic_version")
    if la != ra:
        alembic_mismatch = f"alembic_version {left_label}={la!r} {right_label}={ra!r}"

    return SchemaDiff(
        only_left_tables=only_left_tables,
        only_right_tables=only_right_tables,
        column_diffs=column_diffs,
        constraint_diffs=_symmetric_set_diff(
            left.get("constraints", []), right.get("constraints", []), left_label, right_label
        ),
        index_diffs=_symmetric_set_diff(left.get("indexes", []), right.get("indexes", []), left_label, right_label),
        trigger_diffs=_symmetric_set_diff(left.get("triggers", []), right.get("triggers", []), left_label, right_label),
        sequence_diffs=_symmetric_set_diff(left.get("sequences", []), right.get("sequences", []), left_label, right_label),
        extension_diffs=ext_diffs,
        extension_warnings=ext_warnings,
        alembic_mismatch=alembic_mismatch,
    )


def _symmetric_set_diff(
    left_items: list[str],
    right_items: list[str],
    left_label: str,
    right_label: str,
) -> list[str]:
    ls, rs = set(left_items), set(right_items)
    out: list[str] = []
    for item in sorted(ls - rs):
        out.append(f"ONLY {left_label}: {item}")
    for item in sorted(rs - ls):
        out.append(f"ONLY {right_label}: {item}")
    return out


def catalog_stats(catalog: dict[str, Any]) -> dict[str, Any]:
    columns = catalog.get("columns", {})
    column_count = sum(len(v) for v in columns.values())
    by_type: dict[str, int] = {}
    for sig in catalog.get("constraints", []):
        parts = sig.split("|", 2)
        kind = parts[1] if len(parts) > 1 else "unknown"
        by_type[kind] = by_type.get(kind, 0) + 1
    return {
        "tables": len(catalog.get("tables", [])),
        "columns": column_count,
        "constraints_total": len(catalog.get("constraints", [])),
        "constraints_by_type": by_type,
        "indexes": len(catalog.get("indexes", [])),
        "triggers": len(catalog.get("triggers", [])),
        "sequences": len(catalog.get("sequences", [])),
        "extensions": len(catalog.get("extensions", {})),
    }


def print_coverage_summary(
    left: dict[str, Any],
    right: dict[str, Any],
    diff: SchemaDiff,
    left_label: str,
    right_label: str,
) -> None:
    """Show what was compared (counts); when diff.ok, every row below matched."""
    ls, rs = catalog_stats(left), catalog_stats(right)
    status = "MATCH" if diff.ok else "MISMATCH"
    print(f"=== parity coverage ({status}) ===")
    print(
        "Each row is the number of objects compared between "
        f"{left_label} and {right_label} (full equality required to pass)."
    )
    rows = [
        ("tables", ls["tables"], rs["tables"]),
        ("columns (name+type+null+default+order)", ls["columns"], rs["columns"]),
        ("PRIMARY KEY constraints", ls["constraints_by_type"].get("PRIMARY KEY", 0), rs["constraints_by_type"].get("PRIMARY KEY", 0)),
        ("UNIQUE constraints", ls["constraints_by_type"].get("UNIQUE", 0), rs["constraints_by_type"].get("UNIQUE", 0)),
        ("FOREIGN KEY constraints", ls["constraints_by_type"].get("FOREIGN KEY", 0), rs["constraints_by_type"].get("FOREIGN KEY", 0)),
        ("CHECK constraints (excl. internal NOT NULL)", ls["constraints_by_type"].get("CHECK", 0), rs["constraints_by_type"].get("CHECK", 0)),
        ("EXCLUDE constraints", ls["constraints_by_type"].get("EXCLUDE", 0), rs["constraints_by_type"].get("EXCLUDE", 0)),
        ("indexes (definition, not name)", ls["indexes"], rs["indexes"]),
        ("triggers", ls["triggers"], rs["triggers"]),
        ("sequences", ls["sequences"], rs["sequences"]),
        ("extensions (presence)", ls["extensions"], rs["extensions"]),
    ]
    for name, lv, rv in rows:
        mark = "ok" if lv == rv else "DIFF"
        print(f"  {name}: {left_label}={lv} {right_label}={rv} [{mark}]")
    if diff.ok:
        print(
            "All structural objects above are identical on dev and staging "
            "(byte-for-byte catalog signatures)."
        )


def print_diff_report(
    diff: SchemaDiff,
    left_meta: dict[str, Any],
    right_meta: dict[str, Any],
    left_label: str,
    right_label: str,
) -> None:
    print("=== db_schema_catalog diff ===")
    print(
        f"{left_label}: db={left_meta['database']} host={left_meta.get('server_host')} "
        f"tables={len(left_meta['tables'])} alembic={left_meta.get('alembic_version')}"
    )
    print(
        f"{right_label}: db={right_meta['database']} host={right_meta.get('server_host')} "
        f"tables={len(right_meta['tables'])} alembic={right_meta.get('alembic_version')}"
    )
    sections = [
        ("tables only on " + left_label, diff.only_left_tables),
        ("tables only on " + right_label, diff.only_right_tables),
        ("columns", diff.column_diffs),
        ("constraints", diff.constraint_diffs),
        ("indexes", diff.index_diffs),
        ("triggers", diff.trigger_diffs),
        ("sequences", diff.sequence_diffs),
        ("extensions (errors)", diff.extension_diffs),
        ("extensions (warnings)", diff.extension_warnings),
    ]
    for title, items in sections:
        if not items:
            continue
        print(f"--- {title} ({len(items)}) ---")
        for line in items[:200]:
            print(line)
        if len(items) > 200:
            print(f"... and {len(items) - 200} more")
    if diff.alembic_mismatch:
        print(f"--- alembic ---")
        print(diff.alembic_mismatch)

    print_coverage_summary(left_meta, right_meta, diff, left_label, right_label)


def dump_json(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, indent=2, sort_keys=True)
