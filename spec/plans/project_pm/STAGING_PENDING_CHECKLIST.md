# Staging pending checklist (backend · frontend · validation)

**PM tracker CSV:** [`Mana_Guruji_OCI_PM_Tracker_Staging.csv`](./Mana_Guruji_OCI_PM_Tracker_Staging.csv)  
**Config rollout (ordered):** [`STAGING_CONFIG_ROLLOUT.md`](../STAGING_CONFIG_ROLLOUT.md) · env SSOT: [`ENV_STAGING_REFERENCE.md`](../ENV_STAGING_REFERENCE.md)  
**Last updated:** 2026-10-21  
**Host:** `stg-aio-1` · `140.245.245.201` · API `http://140.245.245.201:8000`

---

## Completed on staging (summary)

| Area | Done |
|------|------|
| IaC | VCN, `stg-aio-1`, optional `stg-redis-1` micro |
| Runtime | `/opt/mana-guruji/venv`, self-hosted GitHub runner |
| Database | `Mana_Guruji`, full migrate + grants |
| Redis | External `18.60.87.153` logical DB 0/1/2 ensured |
| API | systemd `mana-guruji-api`, `/health/live` 200 |
| Network | OCI ingress + `firewall-cmd --reload` for 8000 (and 3000/3001) |
| CD | `deploy-staging.yml` migrate on push to `dev` |
| CORS config | `ALLOWED_ORIGINS` includes admin + public API URLs |

---

## Backend — pending

| ID | Task | Priority |
|----|------|----------|
| STG-S4b | Finish `api.env`: S3 buckets/keys, Razorpay test, `TOTP_ENC_KEYS`, `SECRET_KEY`, optional FCM path | P0 |
| STG-S5 | Confirm **Celery worker + beat** active; broker on Redis **DB 1** after latest code deploy | P0 |
| STG-S6 | `/health/ready` (or full health) not degraded — DB + Redis | P0 |
| STG-S7 | OCI Object Storage — **STG-CFG-001..005** in [`STAGING_CONFIG_ROLLOUT.md`](../STAGING_CONFIG_ROLLOUT.md) | P0 |
| BE-001 | Route **presence** to Redis **DB 2** (`redis_presence_url`) | P2 |
| BE-002 | `bootstrap_admin.py` — first admin for console | P0 |
| BE-003 | Razorpay test webhooks pointed at staging public URL | P1 |
| CI-001b | CI: pytest + full migrate chain on PostGIS service | P0 |
| CI-002 | Build/push arm64 images to OCIR | P1 |

---

## Frontend — pending

| ID | Task | Priority |
|----|------|----------|
| MOB-003 | **Admin UI** — VM Model 2: `./deploy/staging/install_admin.sh` → `http://140.245.245.201:3000`; laptop dev optional | P0 |
| MOB-004 | Admin login + console smoke (bookings/catalog/TDS pages load) | P0 |
| MOB-001 | **Flutter customer**: `--dart-define=API_BASE_URL=http://140.245.245.201:8000` or device APK | P1 |
| MOB-002 | **Flutter partner**: same base URL; dispatch/heartbeat smoke | P1 |
| MOB-003b | IaC/scripts: `install_admin.sh`, `mana-guruji-admin.service`, `admin_only` deploy component | P0 |
| — | HTTPS + admin domain (production pattern) | Prod |

**Note:** Flutter does not use browser CORS; admin **does** — keep `ALLOWED_ORIGINS` aligned with `http://localhost:3000` (and `127.0.0.1:3000`).

---

## Validation — pending

| ID | Task | How |
|----|------|-----|
| VAL-001 | Schema vs `spec/db` | Actions → **DB verify** or `verify_database_schema.py --strict` |
| VAL-002 | Dev vs staging DB parity | Laptop: `DB_DEV_STAGING_PARITY.md` / `Run-DbDevStagingParity.ps1`; deep `compare_database_schemas.py` |
| VAL-003 | Celery | `systemctl status` worker/beat; `redis-cli -h 18.60.87.153 -n 1 KEYS '*'` after tasks |
| VAL-004 | **MVP A–F** on staging | [`MVP_GO_NO_GO_CHECKLIST.md`](../MVP_GO_NO_GO_CHECKLIST.md) |
| VAL-005 | TDS readiness strict | `check_tds_readiness --strict` on staging DB |

---

## Suggested order (next 1–2 weeks)

1. **BE-002** + **MOB-003/004** — admin against staging API  
2. **STG-S5** — Celery verification (**VAL-003**)  
3. **VAL-001** + **VAL-004** — DB + MVP gate  
4. **MOB-001/002** — Flutter device smoke  
5. **STG-CFG Phase 1–2** — OCI buckets + `bootstrap_catalog.py` + storage smoke workflow  
6. **BE-003** — Razorpay webhooks  

**Production:** blocked until **STG-S6** + **VAL-004** marked **Completed** in CSV.
