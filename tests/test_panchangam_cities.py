"""Panchangam city registry (§23.6.1)."""
from __future__ import annotations

from app.services.panchangam_cities import PANCHANGAM_CITIES, resolve_city


def test_resolve_city_hyderabad_case_insensitive():
    meta = resolve_city("Hyderabad")
    assert meta is not None
    assert meta["display"] == "Hyderabad"
    assert meta["lat"] == 17.38500
    assert meta["lng"] == 78.48600
    assert meta["tz"] == "Asia/Kolkata"


def test_resolve_city_unknown():
    assert resolve_city("Mumbai") is None


def test_registry_has_hyderabad():
    assert "hyderabad" in PANCHANGAM_CITIES
