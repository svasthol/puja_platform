"""Unified profile — GET /v1/me (customer + partner). Trust card + published photo when flag on."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status as http
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_customer_or_pujari
from app.db.engine import get_db
from app.services.trust_card import (
    fetch_partner_profile_header,
    load_feature_trust_card_enabled,
    normalize_public_name_candidate,
    partner_trust_profile_block,
)

router = APIRouter(prefix="/me", tags=["profile"])


class PartnerMeBlock(BaseModel):
    pujari_id: uuid.UUID
    display_name: str
    header_subtitle: str = ""
    public_name: str | None = None
    public_name_pending: str | None = None
    identity_verified: bool
    verification_status: str
    trust_card_enabled: bool = False
    profile_photo_url: str | None = None
    profile_photo_url_expires_in: int | None = None
    public_name_ops_approved: bool = False
    trusted_on_platform: bool = False


class MeResponse(BaseModel):
    app_context: str
    user_id: uuid.UUID
    partner: PartnerMeBlock | None = None
    model_config = {"extra": "ignore"}


@router.get("", response_model=MeResponse)
async def get_me(
    p: Principal = Depends(require_customer_or_pujari),
    db: AsyncSession = Depends(get_db),
):
    if p.app_context == "customer":
        return MeResponse(app_context="customer", user_id=p.user_id)

    pid = (
        await db.execute(
            text("SELECT id FROM pujaris WHERE user_id = :uid"),
            {"uid": str(p.user_id)},
        )
    ).scalar_one_or_none()
    if pid is None:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not a pujari account.")

    row = (
        await db.execute(
            text(
                """
                SELECT p.id, p.public_name, p.public_name_pending, p.verification_status,
                       u.full_name
                FROM pujaris p
                JOIN users u ON u.id = p.user_id
                WHERE p.id = :pid
                """
            ),
            {"pid": str(pid)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Not a pujari account.")

    display, subtitle = await fetch_partner_profile_header(db, row["id"])
    public_name = normalize_public_name_candidate(row["public_name"])
    pending = normalize_public_name_candidate(row["public_name_pending"])

    trust_on = await load_feature_trust_card_enabled(db)
    trust_block: dict[str, Any] | None = None
    if trust_on:
        trust_block = await partner_trust_profile_block(
            db, pujari_id=row["id"], trust_enabled=True
        )

    partner = PartnerMeBlock(
        pujari_id=row["id"],
        display_name=display,
        header_subtitle=subtitle,
        public_name=public_name,
        public_name_pending=pending,
        identity_verified=row["verification_status"] == "verified",
        verification_status=row["verification_status"],
        trust_card_enabled=trust_on,
        profile_photo_url=(trust_block or {}).get("profile_photo_url"),
        profile_photo_url_expires_in=(trust_block or {}).get("profile_photo_url_expires_in"),
        public_name_ops_approved=bool((trust_block or {}).get("public_name_ops_approved")),
        trusted_on_platform=bool((trust_block or {}).get("trusted_on_platform")),
    )
    return MeResponse(
        app_context="pujari",
        user_id=p.user_id,
        partner=partner,
    )
