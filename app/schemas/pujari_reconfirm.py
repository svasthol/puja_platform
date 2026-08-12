"""Partner reconfirm ack response (§23.5)."""
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class PujariReconfirmResponse(BaseModel):
    booking_id: uuid.UUID
    pujari_confirmed_at: dt.datetime
    already_confirmed: bool
