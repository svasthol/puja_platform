"""Canonical city registry for panchangam vendor fetch (§23.6.1)."""
from __future__ import annotations

from typing import TypedDict


class PanchangamCity(TypedDict):
    display: str
    lat: float
    lng: float
    tz: str


PANCHANGAM_CITIES: dict[str, PanchangamCity] = {
    "hyderabad": {
        "display": "Hyderabad",
        "lat": 17.38500,
        "lng": 78.48600,
        "tz": "Asia/Kolkata",
    },
}


def resolve_city(city: str) -> PanchangamCity | None:
    """Case-insensitive lookup; returns canonical display name + coordinates."""
    return PANCHANGAM_CITIES.get(city.strip().lower())
