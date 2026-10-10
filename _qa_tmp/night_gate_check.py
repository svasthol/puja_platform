"""Quick checks: night gate advisory + booking list + instant classification."""
from __future__ import annotations

import datetime as dt
import httpx

BASE = "http://127.0.0.1:8000"
PHONE = "+919300000031"


def login():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        otp = c.post("/v1/auth/otp/request", json={"phone": PHONE}).json()["otp_dev_only"]
        return c.post("/v1/auth/otp/verify", json={"phone": PHONE, "otp": otp, "app_context": "customer"}).json()["access_token"]


def main():
    h = {"Authorization": f"Bearer {login()}"}
    c = httpx.Client(base_url=BASE, timeout=30, headers=h)

    # Near-term night slot (today or tomorrow 23:30) -> expect instant class + night warning
    for label, date, time in [
        ("tonight_2330", dt.date.today().isoformat(), "23:30:00"),
        ("tomorrow_2300", (dt.date.today() + dt.timedelta(days=1)).isoformat(), "23:00:00"),
        ("soon_daytime", (dt.date.today() + dt.timedelta(days=1)).isoformat(), "11:00:00"),
    ]:
        r = c.post("/v1/slot-holds", json={"date": date, "time": time})
        j = r.json() if r.status_code == 201 else {"err": r.text[:150]}
        print(f"[slot-hold {label}] {r.status_code} class={j.get('advisory_booking_class')} warnings={j.get('gate_warnings')}")

    # list bookings
    r = c.get("/v1/bookings?limit=5")
    j = r.json()
    print(f"[GET /v1/bookings] {r.status_code} count={len(j.get('bookings', []))} statuses={[b.get('status') for b in j.get('bookings', [])]}")


if __name__ == "__main__":
    main()
