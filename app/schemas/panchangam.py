"""Panchangam API schemas (§23.6)."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class PanchangamTimeWindow(BaseModel):
    start: str
    end: str


class AuspiciousWindow(BaseModel):
    label: str
    start: str
    end: str


class PanchangamResponse(BaseModel):
    city: str
    date: dt.date
    panchang_system: Literal["drik", "vakya"]
    locale: Literal["te", "en"]
    vaaram: str
    tithi: str
    tithi_end: str | None = None
    nakshatram: str
    nakshatra_end: str | None = None
    yoga: str | None = None
    yoga_end: str | None = None
    rahu_kalam: PanchangamTimeWindow | None = None
    yama_gandam: PanchangamTimeWindow | None = None
    sunrise: str
    sunset: str
    brahma_muhurtam: PanchangamTimeWindow | None = None
    amrita_ghadiya: PanchangamTimeWindow | None = None
    varjyam: PanchangamTimeWindow | None = None
    durmuhurtam: PanchangamTimeWindow | None = None
    auspicious_windows: list[AuspiciousWindow] = Field(default_factory=list)
    fetched_at: dt.datetime
    disclaimer: str
