"""SMS send result — shared across providers and router."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SmsSendResult:
    sent: bool
    provider: str | None = None
    error: str | None = None
