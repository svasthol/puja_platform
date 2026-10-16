"""Diagnose dispatch presence/eligibility visibility."""
from __future__ import annotations

import sys
from dotenv import load_dotenv
load_dotenv()

PUJARI_ID = sys.argv[1] if len(sys.argv) > 1 else None

from app.core.config import get_settings
from app.core.redis_keys import presence_redis_key
import redis as redis_lib

s = get_settings()
print("REDIS_URL:", str(s.REDIS_URL))
r = redis_lib.from_url(str(s.REDIS_URL), socket_connect_timeout=5)
print("ping:", r.ping())

if PUJARI_ID:
    key = presence_redis_key(PUJARI_ID)
    r.set(key, "1", ex=300)
    print(f"set {key} -> readback={r.get(key)!r}")

# how many presence keys exist right now
cnt = 0
sample = []
for k in r.scan_iter(match="presence:*", count=500):
    cnt += 1
    if len(sample) < 5:
        sample.append(k.decode() if isinstance(k, bytes) else k)
print("presence_keys_total:", cnt, "sample:", sample)
