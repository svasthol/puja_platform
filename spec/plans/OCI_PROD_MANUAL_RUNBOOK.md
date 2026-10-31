# OCI production — manual execution runbook (Hyderabad)

**Audience:** Whoever provisions and SSHs into OCI Compute for **first prod cut**.  
**Region:** `ap-hyderabad-1`  
**Companion checklists:** [`OCI_COMPUTE_FLEET.md`](./OCI_COMPUTE_FLEET.md) (**SSOT — shapes/OCPU/RAM/disk**) · [`OCI_PROD_APPLY_SHEET.md`](./OCI_PROD_APPLY_SHEET.md) · [`OCI_DEPLOYMENT_PLAN.md`](./OCI_DEPLOYMENT_PLAN.md) · [`.github/OCI_CI_CD.md`](../../.github/OCI_CI_CD.md)

**Chosen fleet:** Option B (corrected) — see [`infra/oci/fleet.launch.yaml`](../../infra/oci/fleet.launch.yaml).  
**Not chosen:** [`infra/oci/fleet.alternative-9vm.yaml`](../../infra/oci/fleet.alternative-9vm.yaml).

This runbook covers **SSH procedures** only; do not edit OCPU/RAM here — change the SSOT + YAML.

---

## 1. Fleet inventory worksheet (fill when created)

Copy from [`OCI_COMPUTE_FLEET.md` § Inventory](./OCI_COMPUTE_FLEET.md) or fill here before Phase 1 SSH work.

| Hostname | OCID | Private IP | Subnet | SSH user | Shape (as built) | Notes |
|----------|------|------------|--------|----------|------------------|-------|
| app-1 | | | app-private | opc | A1 2/12 | |
| app-2 | | | app-private | opc | A1 2/12 | |
| db-1 | | | data-private | opc | A1 2/12 + 100 GB data | |
| db-2 | | | data-private | opc | A1 2/12 + 100 GB data | |
| cache-1 | | | data-private | opc | A1 1/6 | |
| bastion (optional) | | | public | opc | | |

**DNS (manual):** `api.<domain>` → NLB · `admin.<domain>` → NLB or Object Storage.

---

## 2. Network & security (manual in OCI Console)

Execute in order:

1. **VCN** `mana-guruji-prod` — CIDR e.g. `10.50.0.0/16`.
2. **Subnets:** `public` (NLB), `app-private`, `data-private` (no internet ingress).
3. **IGW** on public; **NAT** on private subnets for egress (Razorpay, FCM, SMS).
4. **Service Gateway** for Object Storage (backup upload without public egress).
5. **NSGs** (minimum rules):

| From | To | Ports | Purpose |
|------|-----|-------|---------|
| NLB | app-1, app-2 | 443, 80 | HTTPS |
| app-* | db-1, db-2 | 5432 | Postgres (Patroni) |
| app-* | db-* | 8008 | Patroni REST (if used) |
| app-* | cache-1, app-2 | 6379 | Redis |
| app-*, cache-1 | app-*, cache-1 | 2379 | etcd |
| app-*, cache-1 | all redis/sentinel hosts | 26379 | Sentinel |
| app-1, app-2 | each other | 5000 | HAProxy PG routing |
| app-* | localhost | 6432 | PgBouncer (local only) |
| Operators | bastion | 22 | SSH |

6. **No public IP** on `db-*`, `cache-1`.

---

## 3. Per-host manual steps (Option B corrected)

Do **db + cache** before **app** bootstrap. Numbers match [`OCI_PROD_APPLY_SHEET.md`](./OCI_PROD_APPLY_SHEET.md).

### 3.1 All hosts — first boot (repeat per VM)

**Where:** SSH via Bastion as `opc`.

```bash
sudo dnf -y update
sudo dnf -y install git jq vim curl tar
# Optional: chrony for time sync
sudo systemctl enable --now chronyd
```

Create app user (app nodes only):

```bash
sudo useradd -r -m -d /opt/mana-guruji -s /bin/bash mana-guruji || true
```

Record hostname:

```bash
sudo hostnamectl set-hostname app-1   # replace per host
```

---

### 3.2 `db-1` and `db-2` — PostgreSQL 16 + PostGIS + Patroni

**MANUAL** until Ansible exists.

1. Attach **100 GB** block volume; mount at `/var/lib/postgresql` (ext4/xfs, `fstab`).
2. Install packages (Oracle Linux 9 — enable PGDG or use approved internal mirror):

```bash
# Example — adjust repo URLs to your approved PG 16 + PostGIS packages for OL9
sudo dnf -y install postgresql16-server postgresql16-contrib postgis34_16
```

3. Install **Patroni** + **etcd** client; configure Patroni cluster name `mana-guruji-prod`.
4. **db-1:** initialize cluster; **db-2:** join as replica.
5. Verify: `patronictl list` shows one leader, one replica.
6. **Do not** expose `:5432` to the internet.

**Superuser:** set `postgres` password; store in **OCI Vault** (`DATABASE_SUPERUSER`).

---

### 3.3 `cache-1` — Redis primary + Sentinel + pgBackRest

1. Install **Redis 7**; enable **AOF** (`appendonly yes`).
2. Install **Sentinel** (same host or co-located); seed monitor for master on `cache-1`.
3. Install **etcd** member (3-node quorum with etcd on app-1, app-2, cache-1 — or your chosen layout).
4. Install **pgBackRest**; configure stanza → **Object Storage** S3-compatible endpoint; run first `backup` / `check`.

---

### 3.4 `app-2` — Redis replica

1. `replicaof <cache-1-private-ip> 6379`
2. Sentinel on app-1, app-2, cache-1 must agree on master.

---

### 3.5 `app-1` and `app-2` — HAProxy, PgBouncer, app stack

**HAProxy** (both app nodes, listen **`:5000`** → Patroni primary):

- Backend: `db-1`/`db-2` `:5432` with health check / Patroni-aware config.

**PgBouncer** (local **`:6432`**, transaction mode):

- Pool to `127.0.0.1:5000` or direct to primary — team choice; migrations **never** use 6432.

**nginx (staging only — not on prod `app-*`):**

- Install on **`stg-aio-1`** only: TLS (Let’s Encrypt or OCI Certificates via OCI DNS), proxy **`:443` → `127.0.0.1:8000`**.
- Production: **OCI NLB** terminates TLS and forwards to uvicorn **`:8000`** — do **not** install nginx on prod app nodes.

**Clone repo** (both app nodes):

```bash
sudo -u mana-guruji git clone https://github.com/svasthol/Guruji.git /opt/mana-guruji/src
cd /opt/mana-guruji/src/puja_platform   # path may vary if monorepo root differs
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Celery:** workers on both nodes; **exactly one** RedBeat/beat process globally (typically **app-1** only).

---

### 3.6 Database bootstrap & migrations (once per new prod DB)

**Jump host:** `app-1` (or Bastion with route to HAProxy `:5000`).

**Extensions (superuser, once):**

```bash
export PGURL='postgresql://postgres:SECRET@<haproxy-vip-or-app-1>:5000/Mana_Guruji'
psql "$PGURL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql "$PGURL" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql "$PGURL" -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
```

**Roles (once):**

```bash
cd /opt/mana-guruji/src/puja_platform
source .venv/bin/activate
export DATABASE_URL='postgresql://postgres:SECRET@<host>:5000/Mana_Guruji'
bash scripts/bootstrap.sh
# Then rotate puja_app / puja_migrate passwords → Vault
```

**Schema (once, then every release via CI):**

```bash
export DATABASE_URL='postgresql://puja_migrate:SECRET@<host>:5000/Mana_Guruji'
alembic upgrade head
# 012–027 scripts, then 028–032 — see MVP_GO_NO_GO_CHECKLIST quick block
python scripts/apply_grants.py
python scripts/check_tds_readiness.py --strict
```

**Runtime env** on app nodes (`/etc/mana-guruji/api.env`):

```bash
DATABASE_URL=postgresql+psycopg://puja_app:SECRET@127.0.0.1:6432/Mana_Guruji
REDIS_URL=redis://:<password>@<sentinel-or-primary>:6379/0
DEBUG=false
```

Start API + workers (systemd units — manual install until quadlets land).

---

### 3.7 NLB + DNS smoke (manual)

```bash
curl -sS "https://api.<domain>/health/live"
curl -sS "https://api.<domain>/health"
```

Register Razorpay/Setu webhooks to `https://api.<domain>/...`.

---

## 4. What is manual vs automated (summary)

| Action | Manual on OCI? |
|--------|----------------|
| Create VMs, volumes, NLB, NSGs, Vault, buckets | **Yes** (Console/Terraform) |
| Install PG, Patroni, Redis, HAProxy, PgBouncer | **Yes** (SSH; later Ansible) |
| `bootstrap.sh` + extensions | **Yes — once** per prod DB |
| `migrate.sh` + `apply_grants.py` | **Yes** until CI; then CI with approval |
| Pull container digest + rolling restart | **CI** (when wired) |
| Flutter / admin deploy | **Manual** separate repo |

---

## 5. Open decisions (fill before prod)

| # | Decision | Your choice | Date |
|---|----------|-------------|------|
| 1 | Bastion SKU / VPN | | |
| 2 | Let’s Encrypt vs OCI Certificates | | |

Scale steps and alternative fleets: [`OCI_COMPUTE_FLEET.md`](./OCI_COMPUTE_FLEET.md).

---

*Procedures only — fleet numbers live in `OCI_COMPUTE_FLEET.md` + `infra/oci/fleet.launch.yaml`.*
