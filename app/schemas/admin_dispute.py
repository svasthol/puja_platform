"""Admin dispute resolution schemas (A-DISPUTE)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class AdminDisputeRequest(BaseModel):
    change_reason: str = Field(..., min_length=3, max_length=500)
    dispute_type: Literal["service", "offline_non_payment"] = "service"


class AdminDisputeResponse(BaseModel):
    booking_id: uuid.UUID
    previous_status: str
    status: str
    dispute_type: str
    disputed_at: dt.datetime
    offline_balance_note: str | None = None
