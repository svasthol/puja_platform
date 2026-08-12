"""Unit tests for catalogue media S3 helpers (no DB)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

from app.services import catalog_media as cm


def test_build_s3_key():
    mid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    key = cm.build_s3_key("puja", mid, "image/png")
    assert key == "catalog/puja/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.png"


def test_public_url_with_cdn_base():
    with patch("app.services.catalog_media.get_settings") as gs:
        gs.return_value.S3_CATALOG_PUBLIC_URL = "https://cdn.test"
        assert cm.public_url("catalog/x.png") == "https://cdn.test/catalog/x.png"


def test_public_url_none_when_unconfigured():
    with patch("app.services.catalog_media.get_settings") as gs:
        gs.return_value.S3_CATALOG_PUBLIC_URL = ""
        assert cm.public_url("catalog/x.png") is None
