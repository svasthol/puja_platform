"""
Live admin catalogue smoke — hits a **running** API (same paths as E2E UI Admin tab).

Skipped when uvicorn is down or admin TOTP env is not set.

Run (API on :8000, admin bootstrapped):

    set ADMIN_TEST_PHONE=+919111111100
    set ADMIN_TOTP_SECRET=<secret from bootstrap_admin.py>
    pytest tests/test_admin_catalog_live.py -q

Env:
    E2E_API_UPSTREAM   default http://127.0.0.1:8000
    ADMIN_TEST_PHONE   admin user phone (must have admin role + TOTP credential)
    ADMIN_TOTP_SECRET  plaintext TOTP secret from bootstrap (dev only)
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_BASE = os.environ.get("E2E_API_UPSTREAM", "http://127.0.0.1:8000").rstrip("/")
ADMIN_PHONE = os.environ.get("ADMIN_TEST_PHONE", "").strip()
ADMIN_SECRET = os.environ.get("ADMIN_TOTP_SECRET", "").strip()
CATALOG = f"{API_BASE}/v1/admin/catalog"


@pytest.fixture(scope="module")
def api_up():
    try:
        with httpx.Client(timeout=3.0) as client:
            res = client.get(f"{API_BASE}/health")
        if res.status_code != 200:
            pytest.skip(f"API unhealthy at {API_BASE}/health → {res.status_code}")
    except httpx.HTTPError as exc:
        pytest.skip(f"API not reachable at {API_BASE}: {exc}")


@pytest.fixture(scope="module")
def admin_token(api_up):
    if not ADMIN_PHONE or not ADMIN_SECRET:
        pytest.skip("Set ADMIN_TEST_PHONE and ADMIN_TOTP_SECRET for live catalogue smoke")
    from app.core import totp

    code = totp.totp_at(ADMIN_SECRET, at=int(time.time()))
    with httpx.Client(timeout=15.0) as client:
        res = client.post(
            f"{API_BASE}/v1/admin/auth/login",
            json={"phone": ADMIN_PHONE, "code": code},
        )
    if res.status_code != 200:
        pytest.skip(f"Admin login failed ({res.status_code}): {res.text}")
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_catalog_smoke(admin_token):
    """Full Wave-1 path: category → puja → content → addon (+ duplicate guard)."""
    suffix = uuid.uuid4().hex[:8]
    cat_name = f"Live-Cat-{suffix}"
    puja_name = f"Live-Puja-{suffix}"

    with httpx.Client(timeout=20.0) as client:
        headers = _auth(admin_token)

        res = client.post(
            f"{CATALOG}/categories",
            headers=headers,
            json={"name": cat_name, "change_reason": "live-smoke"},
        )
        assert res.status_code == 201, res.text
        cat = res.json()
        cat_id = cat["id"]
        assert cat["slug"]

        res = client.put(
            f"{CATALOG}/categories/{cat_id}",
            headers=headers,
            json={"description": "live smoke", "change_reason": "live-smoke"},
        )
        assert res.status_code == 200, res.text

        res = client.post(
            f"{CATALOG}/pujas",
            headers=headers,
            json={
                "category_id": cat_id,
                "name": puja_name,
                "default_price": "1200.00",
                "price_max": "1800.00",
                "duration_minutes": 60,
                "change_reason": "live-smoke",
            },
        )
        assert res.status_code == 201, res.text
        puja = res.json()
        puja_id = puja["id"]

        res = client.get(f"{CATALOG}/pujas/{puja_id}/impact", headers=headers)
        assert res.status_code == 200, res.text
        impact = res.json()
        assert impact["puja_id"] == puja_id

        res = client.put(
            f"{CATALOG}/pujas/{puja_id}/content",
            headers=headers,
            json={
                "kind": "inclusion",
                "items": [
                    {"text": "Flowers", "position": 0},
                    {"text": "Fruits", "position": 1},
                ],
                "change_reason": "live-smoke",
            },
        )
        assert res.status_code == 200, res.text
        assert len(res.json()["items"]) == 2

        res = client.get(
            f"{CATALOG}/pujas/{puja_id}/content",
            headers=headers,
            params={"kind": "inclusion"},
        )
        assert res.status_code == 200, res.text
        assert len(res.json()["items"]) == 2

        res = client.post(
            f"{CATALOG}/pujas/{puja_id}/addons",
            headers=headers,
            json={"name": "Extra diya", "price": "99.00", "change_reason": "live-smoke"},
        )
        assert res.status_code == 201, res.text
        addon_id = res.json()["id"]

        res = client.put(
            f"{CATALOG}/addons/{addon_id}",
            headers=headers,
            json={"is_active": False, "change_reason": "live-smoke"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["is_active"] is False

        res = client.post(
            f"{CATALOG}/categories",
            headers=headers,
            json={"name": cat_name},
        )
        assert res.status_code == 409, res.text
