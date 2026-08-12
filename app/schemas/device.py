"""FCM device registration schemas (B-DEVICE)."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class DeviceRegister(BaseModel):
    device_token: str = Field(min_length=10, max_length=255)
    platform: Literal["android", "ios", "web"] | None = None


class DeviceOut(BaseModel):
    id: uuid.UUID
    device_token: str
    platform: str | None
    last_seen_at: dt.datetime | None
