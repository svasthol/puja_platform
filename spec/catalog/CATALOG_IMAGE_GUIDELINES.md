# Catalogue image guidelines (art direction + ops handoff)

**Goal:** Every category and puja image must make the ritual's **name, purpose and visual
intent instantly clear and attractive** — conversion-grade imagery, not stock filler.

**Pipeline (do not change):** Images are uploaded through **Admin → Catalogue → MediaUploader**
(presign → PUT → confirm), stored in the OCI catalog bucket, and served to the apps only when
`upload_status = 'ready'`. See `spec/plans/SPEC_AMENDMENTS.md` §20.2 and
`app/services/catalog_media.py`.

---

## Hard technical constraints (enforced in code)

| Constraint | Value | Source |
|-----------|-------|--------|
| Allowed formats | **JPEG, PNG, WebP** | `catalog_media.ALLOWED_CONTENT_TYPES` |
| Max file size | **5 MiB** per image | `S3_CATALOG_MAX_BYTES` |
| Object key | `catalog/{entity_type}/{uuid}.{ext}` | §20.2 |
| Entity types | `category`, `puja`, `gallery`, `addon` | `puja_media.entity_type` |
| Served when | `upload_status='ready'` AND `is_active=true` | `catalog_read.media_urls_by_ids` |
| Fallback if missing/broken | Branded placeholder (temple mark) | Flutter `PujaImage` widget |

Because `PujaImage` degrades gracefully, a missing image never breaks a screen — but a *present,
on-brand* image is what drives bookings. Treat imagery as launch-blocking polish, not optional.

---

## Recommended specs by surface

| Surface | Aspect | Recommended px (≥2x) | Notes |
|---------|--------|----------------------|-------|
| Puja **hero** (detail top) | 16:9 | 1600×900 | Full-bleed behind title; keep focal subject centre/left (title overlays) |
| Puja **list thumbnail** | 1:1 | 600×600 | Same hero asset re-decoded small; must read at 74 px |
| Category **tile** (home) | 1:1 | 240×240 | Simple, iconic, high-contrast; reads at 34 px |
| **Gallery** images | 4:3 or 1:1 | 1200×1200 | Optional supporting shots |
| **Addon** thumbnail | 1:1 | 240×240 | Samagri kit / decoration; reads at 40 px |

**Format rule of thumb:** photographic → **WebP** (or JPEG q≈80); flat/graphic → **PNG/WebP**.
Keep each file well under 5 MiB (aim ≤ 400 KB for thumbnails, ≤ 1 MB for heroes).

---

## Art direction per category

Original creative only — reference top temple/seva platforms for *taxonomy*, never copy their
assets or copy. Warm, devotional, authentic Telugu-Hindu context.

| Category (slug) | Visual intent | Composition cues |
|-----------------|---------------|------------------|
| **Vratams** (`vratams`) | Vow + katha warmth | Kalasham with mango toranam, lit deepam, katha booklet; soft gold light |
| **Griha Pravesh & Vastu** (`griha-pravesh-vastu`) | New-home auspicious entry | Threshold with muggu/rangoli, kalasham at doorway, mango leaves |
| **Sanskaras** (`sanskaras`) | Life-milestone tenderness | Family-centric, infant/mother context for naming/annaprashana; gentle, respectful |
| **Homams** (`homams`) | Agni + mantra energy | Homa kundam with controlled flame, samidha, purohit hands offering ahuti |
| **Daily & Special** (`daily-special`) | Everyday devotion | Simple home altar, fresh flowers, single deity focus; bright, uncluttered |
| **Pitru Karyam** (`pitru-karyam`) | Solemn ancestral respect | Muted palette, tarpanam vessels, darbha; dignified, never sombre-morbid |

---

## Per-puja hero checklist

For each of the 22 launch pujas (slugs in `spec/catalog/hyderabad_launch_mdm.csv`):

- [ ] Subject makes the **ritual recognizable at a glance** (deity / act / setup).
- [ ] Reads clearly as a **1:1 thumbnail at 74 px** and as a **16:9 hero**.
- [ ] No baked-in text (the app overlays the localized name/tagline).
- [ ] Consistent warm colour grade across the set (cohesive catalogue look).
- [ ] Culturally accurate props for that specific puja (no generic mismatches).
- [ ] `alt_text` written (concise, descriptive) at upload for accessibility.

---

## Ops handoff workflow

1. Prepare one hero per puja (16:9) + category tiles (1:1), named by **slug**
   (e.g. `satyanarayana-vratam-hero.webp`, `vratams-tile.webp`) for traceability.
2. In **Admin → Catalogue**, open the category/puja and upload via **MediaUploader**
   (this runs presign → PUT → confirm; backend assigns the real `catalog/...` key).
3. Set the uploaded image as **hero** (puja) or **tile image** (category); add gallery shots
   as needed.
4. Fill **alt text** for each image.
5. Verify in the customer app: image appears on list card, detail hero, and category tile with
   no placeholder fallback.

**Note:** slug-named source files are for the ops/MDM handoff only; the stored S3 key is always
`catalog/{entity_type}/{uuid}.{ext}` assigned by the backend.

---

*Last updated: 2026-10-25 · Pairs with `STAGING_CONFIG_ROLLOUT.md` Phase 2 (2.3 image upload).*
