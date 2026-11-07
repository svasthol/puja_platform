"""Customer trust card (Slice A) — public name, feature flag, assignment version."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.booking_gate import _bool_setting
from app.services.kyc_storage import presign_kyc_get

CUSTOMER_PUJARI_FALLBACK = "Your pujari"
_PLACEHOLDER_NAMES = frozenset({"new user", ""})
_PUBLIC_NAME_MAX = 100


def presign_profile_photo_file_url(file_url: object) -> tuple[str | None, int | None]:
    """Presign KYC object key for published profile photo (Slice B)."""
    if not isinstance(file_url, str) or not file_url.strip():
        return None, None
    signed, exp = presign_kyc_get(file_url)
    if not signed:
        return None, None
    return signed, exp if exp and exp > 0 else None


async def load_feature_trust_card_enabled(db: AsyncSession) -> bool:
    row = (
        await db.execute(
            text(
                "SELECT value_json FROM platform_settings "
                "WHERE key = 'feature_trust_card_enabled'"
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    raw = row if isinstance(row, dict) else json.loads(row) if row else {}
    if isinstance(raw, dict) and "enabled" in raw:
        return _bool_setting(raw["enabled"], False)
    return _bool_setting(raw, False)


def normalize_public_name_candidate(raw: str | None) -> str | None:
    if raw is None:
        return None
    name = " ".join(raw.strip().split())
    if not name or name.lower() in _PLACEHOLDER_NAMES:
        return None
    if len(name) > _PUBLIC_NAME_MAX:
        name = name[:_PUBLIC_NAME_MAX].rstrip()
    return name or None


def customer_display_name(public_name: str | None) -> str:
    approved = normalize_public_name_candidate(public_name)
    return approved or CUSTOMER_PUJARI_FALLBACK


def build_customer_trust_pujari(
    *,
    public_name: str | None,
    full_name: str | None = None,
    verification_status: str,
    assignment_version: int,
    rating_avg: Any = None,
    rating_count: int | None = None,
    years_experience: int | None = None,
    profile_photo_url: str | None = None,
    profile_photo_url_expires_in: int | None = None,
    public_name_ops_approved: bool = False,
    public_name_visible: bool = True,
) -> dict[str, Any]:
    """Customer-visible label when trust card is on.

    Prefer an approved **public** name; if none (not set yet or not visible),
    fall back to normalized account **full_name** — same idea as
    ``fetch_partner_profile_header`` so the customer app is not stuck on the
    generic "Your pujari" while identity is verified.
    """
    pub = normalize_public_name_candidate(public_name)
    legal = normalize_public_name_candidate(full_name)
    visible_for_display = pub or legal
    identity_ok = verification_status == "verified"
    visibility_ok = public_name_visible is not False
    trusted = identity_ok and public_name_ops_approved and visibility_ok
    block: dict[str, Any] = {
        "display_name": customer_display_name(visible_for_display),
        "identity_verified": identity_ok,
        "verification_status": verification_status,
        "assignment_version": assignment_version,
        "public_name_ops_approved": public_name_ops_approved,
        "trusted_on_platform": trusted,
    }
    if rating_avg is not None:
        block["rating_avg"] = rating_avg
    if rating_count is not None:
        block["rating_count"] = rating_count
    if years_experience is not None:
        block["years_experience"] = years_experience
    if profile_photo_url:
        block["profile_photo_url"] = profile_photo_url
    if profile_photo_url_expires_in:
        block["profile_photo_url_expires_in"] = profile_photo_url_expires_in
    return block


async def fetch_pujari_row_for_trust(
    db: AsyncSession, pujari_id: uuid.UUID
) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text(
                """
                SELECT p.public_name, p.public_name_visible, p.verification_status,
                       p.rating_avg, p.rating_count, p.years_experience
                FROM pujaris p
                WHERE p.id = :pid
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


async def customer_booking_pujari_payload(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID | None,
    assignment_version: int,
    trust_enabled: bool,
) -> dict[str, Any] | None:
    if pujari_id is None:
        return None
    row = (
        await db.execute(
            text(
                """
                SELECT p.id, u.full_name, p.public_name, p.public_name_visible,
                       p.public_name_approved_at, p.verification_status, p.rating_avg,
                       p.rating_count, p.years_experience,
                       pd_photo.file_url AS profile_photo_file_url
                FROM pujaris p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN pujari_documents pd_photo
                    ON pd_photo.id = p.customer_profile_photo_doc_id
                   AND pd_photo.pujari_id = p.id
                   AND pd_photo.doc_type = 'photo'
                   AND pd_photo.status = 'verified'
                   AND pd_photo.is_current = true
                WHERE p.id = :pid
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    if row is None:
        return None

    if not trust_enabled:
        return {
            "id": row["id"],
            "full_name": row["full_name"],
            "rating_avg": row["rating_avg"],
            "rating_count": row["rating_count"],
            "years_experience": row["years_experience"],
        }

    public_name = row["public_name"]
    public_name_visible = row["public_name_visible"]
    if public_name_visible is False:
        public_name = None

    full_name_for_fallback = (
        row["full_name"] if public_name_visible is not False else None
    )

    approved_at = row.get("public_name_approved_at")
    name_has_ops_approval = approved_at is not None
    pub_vis = row.get("public_name_visible")

    photo_url, photo_expires = presign_profile_photo_file_url(
        row.get("profile_photo_file_url")
    )

    return build_customer_trust_pujari(
        public_name=public_name,
        full_name=full_name_for_fallback,
        verification_status=row["verification_status"],
        assignment_version=assignment_version,
        rating_avg=row["rating_avg"],
        rating_count=row["rating_count"],
        years_experience=row["years_experience"],
        profile_photo_url=photo_url,
        profile_photo_url_expires_in=photo_expires,
        public_name_ops_approved=name_has_ops_approval,
        public_name_visible=pub_vis if pub_vis is not None else True,
    )


async def partner_trust_profile_block(
    db: AsyncSession,
    *,
    pujari_id: uuid.UUID,
    trust_enabled: bool,
    assignment_version: int = 0,
) -> dict[str, Any] | None:
    """Partner-visible trust strip (same semantics as customer `pujari` block)."""
    if not trust_enabled:
        return None
    return await customer_booking_pujari_payload(
        db,
        pujari_id=pujari_id,
        assignment_version=assignment_version,
        trust_enabled=True,
    )


async def seed_public_name_pending(
    db: AsyncSession, pujari_id: uuid.UUID
) -> None:
    """When KYC verifies, propose a customer-safe display name for admin approval."""
    row = (
        await db.execute(
            text(
                """
                SELECT p.public_name, p.public_name_pending, p.verification_status,
                       u.full_name
                FROM pujaris p
                JOIN users u ON u.id = p.user_id
                WHERE p.id = :pid
                FOR UPDATE
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    if row is None or row["verification_status"] != "verified":
        return
    if row["public_name"] is not None or row["public_name_pending"] is not None:
        return

    candidate = normalize_public_name_candidate(row["full_name"])
    if candidate is None:
        return

    await db.execute(
        text(
            """
            UPDATE pujaris
            SET public_name_pending = :name, updated_at = now()
            WHERE id = :pid
            """
        ),
        {"pid": str(pujari_id), "name": candidate},
    )
    await db.execute(
        text(
            """
            INSERT INTO public_name_audit (pujari_id, action, name_value)
            VALUES (:pid, 'proposed', :name)
            """
        ),
        {"pid": str(pujari_id), "name": candidate},
    )


def partner_header_subtitle(spec_label: str | None, city: str | None) -> str:
    parts = [p for p in (spec_label, city) if p]
    return " · ".join(parts) if parts else ""


async def fetch_partner_profile_header(
    db: AsyncSession, pujari_id: uuid.UUID
) -> tuple[str, str]:
    row = (
        await db.execute(
            text(
                """
                SELECT p.public_name, p.public_name_pending, p.verification_status,
                       u.full_name,
                       (
                         SELECT sp.name
                         FROM pujari_specializations ps
                         JOIN specializations sp ON sp.id = ps.specialization_id
                         WHERE ps.pujari_id = p.id
                         ORDER BY sp.name
                         LIMIT 1
                       ) AS spec_name,
                       (
                         SELECT sa.city
                         FROM pujari_service_areas psa
                         JOIN service_areas sa ON sa.id = psa.service_area_id
                         WHERE psa.pujari_id = p.id AND sa.is_active
                         ORDER BY sa.city
                         LIMIT 1
                       ) AS city
                FROM pujaris p
                JOIN users u ON u.id = p.user_id
                WHERE p.id = :pid
                """
            ),
            {"pid": str(pujari_id)},
        )
    ).mappings().first()
    if row is None:
        return "Partner", ""

    display = (
        normalize_public_name_candidate(row["public_name"])
        or normalize_public_name_candidate(row["public_name_pending"])
        or normalize_public_name_candidate(row["full_name"])
        or "Partner"
    )
    subtitle = partner_header_subtitle(row["spec_name"], row["city"])
    return display, subtitle
