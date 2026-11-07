# Trust card — customer booking detail + partner profile (Slices A–C)

Normative API surface remains `spec/API_CONTRACTS.md`. This note ties **product UX** to **existing backend invariants**.

## Customer (`GET /v1/bookings/{id}`, `GET /v1/bookings/{id}/status`)

When `platform_settings.feature_trust_card_enabled` is on, `pujari` is a **trust block** (no raw `full_name` / no pujari `id`).

| Field | Meaning |
|------|---------|
| `display_name` | Customer-safe name (approved `public_name`, else normalized account name when visible). |
| `identity_verified` | `pujaris.verification_status == 'verified'` (Setu + required docs + ops verification pipeline). |
| `trusted_on_platform` | **Both**: identity verified **and** ops-approved public name (`public_name_approved_at IS NOT NULL`). Use for a distinct **“Trusted”** badge vs verification-only. |
| `public_name_ops_approved` | Whether a public display name was approved by ops (`public_name_approved_at IS NOT NULL`). |
| `profile_photo_url` / `profile_photo_url_expires_in` | Present only when ops approved the current `photo` doc and `customer_profile_photo_doc_id` points at it (Slice B). Presigned GET; refresh before expiry. |
| `assignment_version` | Bumps on reassignment; poll `/status` or WS `status_changed`. |

**Photo changes (Slice C):** Partner uploads a new selfie via the **same** KYC document flow → new row goes **`pending`** (prior verified row may remain in history; `is_current` points at the new upload) → ops **approve** in admin KYC → `customer_profile_photo_doc_id` updates (`profile_photo_publish`). **Until approval**, `GET /v1/me` and customer `pujari.profile_photo_url` continue to reflect the **last published** photo (or omit URL if pointer was cleared). Customers never see a pending/rejected photo.

**Partner app (Slice C):** After the first photo is **verified**, KYC hub exposes **Change profile photo** (re-upload). Copy must state that **customers keep the previous published photo** until ops approves. Optional: partner shell header shows `partner.profile_photo_url` when `trust_card_enabled` (same avatar customers see when published).

## Partner (`GET /v1/me`)

Same published photo + trust flags as above (`partner.profile_photo_url`, `trusted_on_platform`, etc.) so the partner app can show **the same** avatar customers see after ops publish it.

## Partner booking detail (`GET /v1/pujari/bookings/{id}`)

Includes optional `partner_self` with the same trust strip when the global trust feature flag is on — useful for a consistent header after confirm.

## Feature flag

`feature_trust_card_enabled` (`platform_settings`). When **off**, customer routes keep the **legacy** `pujari` shape (`id`, `full_name`, …) and partner responses omit trust-only fields.
