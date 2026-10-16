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
3. On VM as `opc`, follow GitHub’s commands. When `./config.sh` asks for labels, include **`staging`** (defaults already add `self-hosted`, `Linux`, `ARM64`), e.g. `--labels staging` or accept defaults then add `staging` in the prompt.
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

---

## Troubleshooting — runner service `status=203/EXEC`

**Symptom:** `sudo ./svc.sh start` → `Main process exited, code=exited, status=203/EXEC`.

| Cause | Fix |
|-------|-----|
| Wrong runner **architecture** (x64 tarball on **aarch64** VM) | Re-download **linux-arm64** from GitHub → **Settings → Actions → Runners → New** |
| `runsvc.sh` not executable or CRLF line endings | `chmod +x runsvc.sh bin/Runner.Listener`; `sudo dnf -y install dos2unix && dos2unix runsvc.sh` |
| Incomplete extract | `cd ~/actions-runner && ls -la runsvc.sh bin/Runner.Listener` — both must exist |

```bash
cd ~/actions-runner
sudo ./svc.sh stop || true
sudo ./svc.sh uninstall || true
# Re-extract official linux-arm64 package from GitHub UI, then:
chmod +x runsvc.sh config.sh svc.sh bin/Runner.Listener
./config.sh --url https://github.com/svasthol/puja_platform --token <TOKEN> --labels staging
sudo ./svc.sh install opc
sudo ./svc.sh start
sudo ./svc.sh status
journalctl -u 'actions.runner.*' -n 30 --no-pager
```

Runner **Idle** in GitHub before re-running **Deploy staging**.

### Permission denied on `runsvc.sh` (journal shows `203/EXEC`)

OL9 **SELinux** or **home directory permissions** often block systemd from executing `~/actions-runner/runsvc.sh`.

On the VM (after clone):

```bash
cd /opt/mana-guruji/src/puja_platform
chmod +x scripts/linux/fix_github_actions_runner_ol9.sh
./scripts/linux/fix_github_actions_runner_ol9.sh
```

Manual checks:

```bash
ls -la /home/opc/actions-runner/runsvc.sh
ls -la /home/opc
getenforce   # if Enforcing and still failing: sudo restorecon -Rv ~/actions-runner
```

Remove duplicate units if install said **exists**:

```bash
sudo rm -f /etc/systemd/system/actions.runner.*.service
sudo systemctl daemon-reload
```

**Do not** set `STAGING_REPO_DIR` in the SSH shell — that is a **GitHub repository variable** (Settings → Variables), not a bash command on the VM.
