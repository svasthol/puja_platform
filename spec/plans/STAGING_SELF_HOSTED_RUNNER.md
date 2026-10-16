# Staging deploy via self-hosted runner (workflow-only on VM)

**Problem:** `deploy-staging.yml` job **SSH deploy** runs on GitHub’s cloud and connects to `stg-aio-1:22`. OCI ingress allows only your laptop IP (`ssh_allowed_cidrs`), so SSH **times out** from Actions.

**Solution:** Install a [GitHub Actions self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners) **on `stg-aio-1`**. The deploy job runs **on the VM** and executes the same `remote_staging_deploy.sh` as SSH would — no inbound SSH from the internet.

**CI (`ci.yml`)** still runs on `ubuntu-24.04-arm` in GitHub — it only **verifies** `pip install -r requirements.txt` + imports. It does **not** install Python on staging.

---

## One-time: OS packages + clone (minimal manual)

The runner and deploy script need `git` and a clone (you already did):

- Repo: `/opt/mana-guruji/src/puja_platform`
- Optional RPMs: `sudo dnf -y install git python3.12 python3.12-pip python3.12-devel gcc gcc-c++ make openssl-devel libffi-devel`

Everything else (pip venv, PG/Redis, migrate) can be driven by **Deploy staging** workflow once the runner is registered.

---

## Register runner on `stg-aio-1`

1. GitHub → **svasthol/puja_platform** → **Settings** → **Actions** → **Runners** → **New self-hosted runner**.
2. OS: **Linux**, Arch: **ARM64**.
3. On VM as `opc`, follow GitHub’s commands (download, configure). Suggested labels when prompted: `self-hosted`, `linux`, `arm64`, `staging`.
4. Install as a **service** so it survives reboot (`sudo ./svc.sh install` per GitHub instructions).
5. Repo → **Settings** → **Secrets and variables** → **Actions** → **Variables** → New repository variable:
   - Name: `STAGING_DEPLOY_MODE`
   - Value: `self-hosted`

With that variable set, `deploy-staging.yml` runs the **Deploy on VM (self-hosted)** job instead of SSH.

---

## Workflow behavior

| `STAGING_DEPLOY_MODE` | Deploy job | Where Python/libs install |
|------------------------|------------|---------------------------|
| unset or `ssh` | SSH from GitHub (needs open port 22 to GitHub IPs) | On VM via `remote_staging_deploy.sh` |
| `self-hosted` | Job runs **on stg-aio-1** | Same script — `bootstrap_python_runtime.sh` → `/opt/mana-guruji/venv` |

Manual **Run workflow** inputs still apply: `run_data_services`, `run_db_bootstrap`, `run_python_bootstrap`, `run_migrate`.

---

## After runner is online

1. Push to `dev` or **Actions → Deploy staging → Run workflow**.
2. First time: enable **run_data_services** and **run_db_bootstrap** (after `api.env` exists).
3. Confirm job **Deploy on VM (self-hosted)** is green.

Revert to SSH mode only if you add Bastion or widen ingress (not recommended).
