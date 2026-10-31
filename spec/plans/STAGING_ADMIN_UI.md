# Staging Admin UI (Model 2 — on `stg-aio-1`)

**Host:** `stg-aio-1` · **URL:** `http://140.245.245.201:3000` (lock OCI ingress + firewalld to ops `/32`)

Admin runs as **Next.js production** (`next start`) beside the API. Laptop `npm run dev` remains valid for local work.

## One-time on VM

```bash
cd /opt/mana-guruji/src/puja_platform
git pull origin dev
chmod +x deploy/staging/install_admin.sh scripts/linux/ensure_node_ol9.sh
./deploy/staging/install_admin.sh
```

Creates `/etc/mana-guruji/admin.env` from `deploy/env/staging.admin.env.example` if missing.

**API CORS** — add the admin browser origin to `/etc/mana-guruji/api.env`:

```json
"http://140.245.245.201:3000"
```

inside `ALLOWED_ORIGINS`, then:

```bash
sudo systemctl restart mana-guruji-api
```

## systemd

| Unit | Port | Config |
|------|------|--------|
| `mana-guruji-admin` | 3000 | `/etc/mana-guruji/admin.env` |

```bash
sudo systemctl status mana-guruji-admin
journalctl -u mana-guruji-admin -f
```

## CD (GitHub Actions)

| `component` | Admin |
|-------------|--------|
| `full` | Rebuild admin **if** `/etc/mana-guruji/admin.env` exists (opt-in after one-time install below) |
| `admin_only` | Admin only (no migrate / API pip) |
| `install_systemd` | Copies all unit files including admin (no build) |

Push to `dev` with `admin_ui/**` or `deploy/**` changes triggers deploy when paths match.

## Build failed: `Cannot find module 'tailwindcss'`

`admin.env` must **not** set `NODE_ENV=production` before `npm ci` (npm skips devDependencies). Remove that line from `/etc/mana-guruji/admin.env`, then:

```bash
cd /opt/mana-guruji/src/puja_platform/admin_ui
rm -rf node_modules
unset NODE_ENV
export NEXT_PUBLIC_API_URL=http://140.245.245.201:8000/v1
npm ci
npm run build
cd .. && ./deploy/staging/install_admin.sh
```

Or `git pull` after the `install_admin.sh` fix on `dev` and re-run the script.

## Change API URL

Edit `NEXT_PUBLIC_API_URL` in `/etc/mana-guruji/admin.env`, then re-run `./deploy/staging/install_admin.sh` (rebuild required).

## Files

| Path | Role |
|------|------|
| `deploy/staging/install_admin.sh` | Node + build + unit + restart |
| `scripts/linux/ensure_node_ol9.sh` | NodeSource 22 on OL9 |
| `deploy/systemd/mana-guruji-admin.service` | systemd unit |
| `deploy/env/staging.admin.env.example` | Template for `admin.env` |
