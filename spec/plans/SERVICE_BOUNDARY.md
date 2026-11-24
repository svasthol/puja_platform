# Service boundary (Hyderabad launch) — §21.13

Polygon gate for **customer** address save and **checkout** when `platform_settings.service_boundary_enabled` is true. Server is authoritative; Flutter bundles `assets/geo/hyderabad_launch_service.geojson` for map UX only.

## Artifacts

| Path | Role |
|------|------|
| `spec/geo/hyderabad_launch_service.geojson` | Launch polygon (replace placeholder with ops-simplified boundary) |
| `spec/geo/hyderabad_launch_service_qa.json` | Unit-test lat/lng vectors |
| `spec/db/migration_041.sql` | Seeds `service_boundary_enabled` = false |
| `scripts/apply_migration_041.py` | Apply migration 041 |

## Env

- `SERVICE_BOUNDARY_GEOJSON_PATH` — optional override; default resolves under `spec/geo/`.

API process **fails startup** if the GeoJSON file is missing or invalid (toggle can stay off until ops enables).

## Admin console

**Settings → Service boundary**

1. **Status** — loaded, etag, vertex count, bbox.
2. **Probe** — test a lat/lng against the polygon.
3. **Reload** — after deploy/replace GeoJSON on disk.
4. **Toggle** — enable enforcement only when polygon is loaded (503 if not).
5. **Download GeoJSON** — audit / diff.

## Rollout checklist

1. Apply migration 041 on staging/production.
2. Deploy API image with `spec/geo/` included.
3. Admin → probe inside/outside QA pins from `hyderabad_launch_service_qa.json`.
4. Enable toggle in **staging**; verify address create + checkout reject outside polygon (`422`, code `OUT_OF_SERVICE_AREA`).
5. Ship mobile build with bundled geo asset; confirm map overlay and save guard when `app-config.service_boundary_enabled` is true.
6. Enable production toggle after sign-off.

## Public API

- `GET /v1/serviceability?lat=&lng=` — probe (no auth).
- `GET /v1/serviceability/boundary` — outline GeoJSON + ETag.

## Errors

- Customer APIs: HTTP 422, body `code: OUT_OF_SERVICE_AREA` when enforcement is on and pin is outside polygon.

Partner dispatch and heartbeat are **out of scope** for this launch slice.