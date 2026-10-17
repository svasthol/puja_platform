# Staging deploy incidents & production guardrails

**Purpose:** Record what broke on **stg-aio-1** so **production** uses IaC + pipelines without repeating manual discovery.

**Related:** [`STAGING_DEPLOY_PIPELINE.md`](./STAGING_DEPLOY_PIPELINE.md) · [`STAGING_SELF_HOSTED_RUNNER.md`](./STAGING_SELF_HOSTED_RUNNER.md) · [`STAGING_REDIS_MICRO.md`](./STAGING_REDIS_MICRO.md)

---

## Incident log (staging)

| # | Symptom | Root cause | Fix in repo / ops |
|---|---------|------------|-------------------|
| 1 | CI `Unable to resolve action` | Wrong pinned action SHAs in workflows | Correct SHAs in `.github/workflows/*.yml` |
| 2 | CI import failures `boto3`, `prometheus_client` | `requirements.txt` behind `pyproject.toml` | Regenerate `requirements.txt` |
| 3 | Deploy `Missing STAGING_HOST` | Secrets in `.env` not GitHub Environment | `STAGING_*` only under **Environments → staging** |
| 4 | Deploy SSH `Connection timed out` | OCI ingress SSH only laptop `/32` | **Self-hosted runner** on VM; `STAGING_DEPLOY_MODE=self-hosted` |
| 5 | Job stuck `Waiting for a runner` | Workflow required label **`staging`**; runner had only `self-hosted, Linux, ARM64` | `runs-on: [self-hosted, Linux, ARM64]` (no extra label) |
| 6 | Runner `203/EXEC` / Permission denied | SELinux + `~/actions-runner` execute context | `semanage fcontext -a -t bin_t "/home/opc/actions-runner(/.*)?"` + `restorecon`; see runner doc |
| 7 | `dnf` 404 `pgdg-common` / `pgdg18` | PGDG `$releasever` broken on **OL9 aarch64** | `scripts/linux/pgdg_ol9_fixup.sh` — pinned repos |
| 8 | `bootstrap` / `dnf` fails after partial PGDG | Broken repos still enabled | `pgdg_ol9_fixup` disables stock PGDG; bootstrap uses `--disablerepo=pgdg*` |
| 9 | `postgis34_16` missing GDAL/GEOS/PROJ | Only `pgdg16` enabled; PostGIS needs **common + extras** | Pinned `pgdg-common-ol9-aarch64`, `pgdg-extras-ol9-aarch64` + optional **CRB** |
| 10 | `bash\r: No such file` on scripts | CRLF from Windows edit | `.gitattributes` `scripts/linux/** eol=lf` |
| 11 | Wrong clone path | Docs said `Guruji.git`; remote is `puja_platform` | Clone to `/opt/mana-guruji/src/puja_platform` |
| 12 | No venv at `/opt/mana-guruji/venv` | Bootstrap never completed | Fix PGDG first; `VENV_DIR=/opt/mana-guruji/venv` |
| 13 | Deploy fails at `migrate.sh` | No `/etc/mana-guruji/api.env` yet | Create `api.env` first; deploy skips migrate until file exists |
| 14 | PostGIS missing `hdf5`, `xerces-c` | PGDG extras incomplete on OL9 aarch64 | Install from OL9/EPEL/CRB before `postgis34_16`; see `install_data_services_ol9.sh` |
| 15 | `pgdg16 listed more than once` | Old + pinned repo files | `pgdg_ol9_fixup.sh` removes duplicates |
| 16 | `ALLOWED_ORIGINS` JSONDecodeError on migrate | `api.env` value not valid JSON array | Use `ALLOWED_ORIGINS=["http://localhost:3000"]` (double quotes); see `deploy/env/staging.api.env.example` |
| 17 | `invalid interpolation syntax` at `%40` in DB URL | Alembic `set_main_option` + ConfigParser vs URL-encoded `@` in password | Fixed in `migrations/env.py` — pass URL from settings, not ini interpolation; keep `%40` in connection strings |

---

## Production checklist (do before prod fleet)

| Area | Staging lesson | Prod requirement |
|------|----------------|------------------|
| **Network** | No GitHub → public SSH | Self-hosted runner **or** Bastion; private SSH app↔DB |
| **Secrets** | Not in laptop `.env` | OCI Vault + GitHub Environments; no keys in git |
| **OS packages** | OL9 aarch64 PGDG pins | Same `pgdg_ol9_fixup.sh` in Ansible/cloud-init for **app/db** roles |
| **PostGIS** | Needs PGDG common+extras+CRB | Bake into DB node image or Ansible role; verify `CREATE EXTENSION postgis` in smoke |
| **Runner** | SELinux `bin_t` on runner dir | Document in prod runbook; or runner on dedicated user `/opt/actions-runner` |
| **Labels** | Workflow `runs-on` must match runner | Register prod runners with documented labels; test queue pickup |
| **CI vs CD** | CI does not install on hosts | Prod: build once (arm64), promote digest; migrate on DB role |
| **Redis** | Optional E2 Micro + Docker | Prod: `cache-1` per `fleet.launch.yaml`; not on app A1 |
| **Paths** | `/opt/mana-guruji/venv`, `api.env` | Same conventions in systemd + `fleet.launch.yaml` |
| **api.env** | JSON `ALLOWED_ORIGINS`; `%40` in DB URLs | Ship `staging.api.env.example`; Alembic must not use ConfigParser for migrate URL |

---

## Verify after any staging change

```bash
# On stg-aio-1
/opt/mana-guruji/venv/bin/python scripts/verify_linux_runtime.py
sudo systemctl is-active postgresql-16
psql -h 127.0.0.1 -U postgres -c 'SELECT PostGIS_Version();'  # after DB up
```

GitHub: runner **Idle** → **Deploy staging** (self-hosted job) green → `curl http://127.0.0.1:8000/health/live`.

---

*Update this file when a new staging-only surprise is found; link PRs that fix scripts/IaC.*
