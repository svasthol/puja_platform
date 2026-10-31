from scripts.db_schema_catalog import diff_catalogs, _is_internal_not_null_check


def _minimal_catalog(tables: list[str], alembic: str = "011") -> dict:
    return {
        "database": "test",
        "server_host": "127.0.0.1",
        "extensions": {"postgis": "3.4.0"},
        "tables": tables,
        "columns": {t: [f"{t}.id|uuid|null=NO|def=|ord=1"] for t in tables},
        "constraints": [],
        "indexes": [],
        "triggers": [],
        "sequences": [],
        "alembic_version": alembic,
    }


def test_diff_ok_when_identical():
    a = _minimal_catalog(["users", "bookings"])
    b = _minimal_catalog(["users", "bookings"])
    d = diff_catalogs(a, b, "dev", "staging")
    assert d.ok


def test_diff_missing_table_on_staging():
    a = _minimal_catalog(["users", "bookings"])
    b = _minimal_catalog(["users"])
    d = diff_catalogs(a, b, "dev", "staging")
    assert not d.ok
    assert d.only_left_tables == ["bookings"]


def test_internal_not_null_check_detected():
    assert _is_internal_not_null_check("2200_172403_1_not_null", "id IS NOT NULL")


def test_postgis_version_mismatch_is_warning_not_error():
    a = _minimal_catalog(["users"])
    b = _minimal_catalog(["users"])
    a["extensions"] = {"postgis": "3.5.3", "pgcrypto": "1.3"}
    b["extensions"] = {"postgis": "3.4.6", "pgcrypto": "1.3"}
    d = diff_catalogs(a, b, "dev", "staging")
    assert d.ok
    assert d.extension_warnings
    assert not d.extension_diffs
