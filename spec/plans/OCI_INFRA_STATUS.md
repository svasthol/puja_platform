# OCI infrastructure & IaC status

**Single tracker for Oracle Cloud provisioning and Terraform.** Update in the same change as infra work.  
**Compute SSOT:** [`OCI_COMPUTE_FLEET.md`](./OCI_COMPUTE_FLEET.md) · [`infra/oci/fleet.launch.yaml`](../../infra/oci/fleet.launch.yaml)

**Region:** `ap-hyderabad-1` · **Object Storage namespace:** set at apply time (CLI: `oci os ns get`)

---

## Summary

| Area | Status | Notes |
|------|--------|-------|
| Fleet spec in git | **DONE** | `OCI_COMPUTE_FLEET.md`, `fleet.launch.yaml` |
| Local OCI API auth | **DONE** | `puja_platform/.oci/` + `Set-OciConfig.ps1` |
| Staging compartment `mana-guruji-staging` | **DONE** | See [`OCI_COMPARTMENTS.md`](./OCI_COMPARTMENTS.md) |
| Terraform staging (`stg-aio-1`) | **COMPUTE LIVE** | `terraform apply` **2026-10-16** — instance `RUNNING` (see inventory) |
| Terraform production (5-node) | **NOT STARTED** | After staging validated |
| Ansible (PG/Redis/app) | **NOT STARTED** | Post-compute |
| GitHub `infra-terraform.yml` | **NOT STARTED** | Plan on PR after staging apply works locally |

---

## Staging — `stg-aio-1`

| Step | Status | Owner / date |
|------|--------|----------------|
| Staging compartment `mana-guruji-staging` | ☑ | 2026-10-10 — CLI `oci iam compartment create` |
| `terraform.tfvars` — `compartment_id` from compartment list | ☐ | |
| `terraform init` / `plan` / `apply` | ☑ | 2026-10-16 — `stg-aio-1` created |
| Record OCID + public IP in inventory below | ☑ | from `terraform output` / state |
| SSH `opc@<public_ip>` | ☐ | from operator home IP (`ssh_allowed_cidrs`) |
| OL9: Python 3.12 + `pip install -r requirements.txt` (aarch64) | ☐ | |
| PG16 + PostGIS + Redis on box | ☐ | |
| `bootstrap.sh` + migrations on staging DB | ☐ | |
| `/health` smoke | ☐ | |

### Staging inventory (fill after `terraform apply`)

| Field | Value |
|-------|--------|
| Compartment OCID | `ocid1.compartment.oc1..aaaaaaaa5xohq3lgwboxcwmvd4vcb5a6zelv3wva4t5kl42zegmjcf2puopq` |
| Instance OCID (`stg_aio_instance_id`) | `ocid1.instance.oc1.ap-hyderabad-1.anuhsljrqscm3aicascrsizfmzsit75oxq6op7b55pwylb52njfqlbvlukjq` |
| Public IP | `140.245.245.201` |
| Private IP | `10.60.1.98` |
| VCN OCID | `ocid1.vcn.oc1.ap-hyderabad-1.amaaaaaaqscm3aiaio4bo7hfulvnbin56bhcl5thhbpo3pmhxhe7ydd2s6aa` |
| Subnet OCID | `ocid1.subnet.oc1.ap-hyderabad-1.aaaaaaaaxfp7fou2vo3oenka6wu5fepeu4idsh3eslxnj2yzheyuuud7nvpa` |
| Shape / AD / FD | `VM.Standard.A1.Flex` 1 OCPU / 6 GB · `aeXz:AP-HYDERABAD-1-AD-1` · `FAULT-DOMAIN-1` |
| Boot volume | 50 GB |
| SSH | `ssh opc@140.245.245.201` |

---

## Troubleshooting — `bootVolumeQuota` on `terraform apply`

**Symptom:** `400-QuotaExceeded, bootVolumeQuota Service limit reached` on `oci_core_instance`.

| Cause | What to do |
|-------|------------|
| **H1** — Boot volume **count/storage** limit in tenancy/compartment | Console → **Governance → Limits, Quotas and Usage** → Block Storage / Boot volumes; or run `Check-OciBootVolumeQuota.ps1` |
| **H2** — **50 GB** boot + existing volumes exceeds free tier | Delete unused boot volumes in Console (do **not** go below **50 GB** — OL9 image minimum) |
| **H3** — **Orphan** boot volumes from failed launches | Console → **Storage → Boot Volumes** → terminate **Available** volumes you do not need |
| **H4** — Need more quota | Tenancy admin: **Request a service limit increase** for Block Storage / Boot volume GB |

VCN/subnet from a partial apply are already in state; after fixing quota, run **`terraform apply` again** (only the instance should be created).

### `InvalidParameter` — tag keys contain forbidden characters

Use **underscores** in freeform tag **keys** (no `.` in keys). Fixed in `modules/staging_stack/main.tf` (`mana_guruji_environment`, etc.).

### `500-InternalError, Out of host capacity` (A1 / Ampere)

**Not a Terraform bug.** OCI has **no free Ampere (A1) physical host** in that **availability domain** right now for `VM.Standard.A1.Flex`. Quota and tags can be fine; launch still fails.

**What to do (in order):**

1. **Retry** — run `terraform apply` again later (off-peak hours, early morning IST). This is the main fix Oracle describes for temporary A1 shortage. Scheduled task: `Invoke-StagingTerraformApplyOnce.ps1` / `ManaGuruji-StagingTerraformRetry`.
2. **Availability domains in Hyderabad** — `ap-hyderabad-1` has **one** AD (Terraform state: `aeXz:AP-HYDERABAD-1-AD-1` only). `availability_domain_name` override does **not** help here; AD cycling only applies in **multi-AD** regions.
3. **Fault domains (FD 1–3)** — staging Terraform does **not** set `fault_domain`; OCI picks one when placing the VM. Pinning or rotating FD is a **long shot** (anecdotal); do not expect it to fix capacity. Retries already re-attempt launch in the same AD.
4. **Shape** — keep **1 OCPU / 6 GB** `VM.Standard.A1.Flex` (smallest request; matches fleet SSOT).
5. **Console probe** — Compute → Create instance → same shape and AD. If Console also fails with out of capacity, wait or open a support ticket.
6. **Support** — OCI **Create service request**: Ampere A1 capacity in `ap-hyderabad-1` for compartment `mana-guruji-staging`.
7. **Do not** lower boot volume below **50 GB** for this OL9 image.
8. **Deadline** — if A1 still fails after **~48–72 h** of retries, use a **paid** flexible shape for staging only (e.g. `VM.Standard.E4.Flex` on Pay As You Go) or pause and revisit; prod fleet SSOT remains **A1** unless explicitly changed.

Network (VCN/subnet) is already created; successful apply only adds the instance.

### A1 capacity — automatic retry on laptop

Optional script: `infra/oci/scripts/Retry-StagingTerraformApply.ps1` (default **10 minutes** between tries).

```powershell
. infra\oci\scripts\Set-OciConfig.ps1
.\infra\oci\scripts\Retry-StagingTerraformApply.ps1 -IntervalMinutes 10
```

**Rules:** one loop only; do **not** create the same VM manually in Console at the same time; stop the loop with **Ctrl+C** after success. Log: `environments/staging/retry-apply.log` (gitignored via `*.log` in staging if added — log is local only).

**OCI rate limits:** spaced retries (5–15 min) are fine. Avoid hammering every few seconds — unnecessary and may hit API throttling.

**Sleep / lid closed:** Nothing runs while the PC is **asleep or hibernating**. Choose one:

| Approach | Command |
|----------|---------|
| **Keep awake** while looping | `Retry-StagingTerraformApply.ps1` — calls Windows API to block system sleep (plug in AC; lid open or set “do nothing on lid close”) |
| **Retry after wake / on a timer** | `Register-StagingTerraformRetryTask.ps1 -IntervalMinutes 15` — uses `schtasks /SC MINUTE /MO 15` (fixed; no `TimeSpan.MaxValue` error). Test: `schtasks /Run /TN ManaGuruji-StagingTerraformRetry` |
| **Manual power settings** (optional) | `powercfg /change standby-timeout-ac 0` (restore later with `powercfg /change standby-timeout-ac 30`) |

Remove scheduled task: `Unregister-ScheduledTask -TaskName ManaGuruji-StagingTerraformRetry -Confirm:$false`

```powershell
. infra\oci\scripts\Set-OciConfig.ps1
.\infra\oci\scripts\Check-OciBootVolumeQuota.ps1 -CompartmentId "<your-staging-compartment-ocid>"
```

---

## Production — Option B (corrected)

| Step | Status |
|------|--------|
| Prod compartment `mana-guruji-production` (same CLI pattern as staging) | ☐ | [`OCI_COMPARTMENTS.md`](./OCI_COMPARTMENTS.md) |
| Prod VCN `10.50.0.0/16` + 5-node fleet | ☐ |
| `app-1`, `app-2`, `db-1`, `db-2`, `cache-1` | ☐ |
| NLB + DNS | ☐ |
| Terraform `environments/production/` | ☐ NOT STARTED |

---

## Terraform paths

| Environment | Directory |
|-------------|-----------|
| Staging | [`infra/oci/terraform/environments/staging`](../../infra/oci/terraform/environments/staging) |
| Production | *planned* `infra/oci/terraform/environments/production` |

---

## Change log

| Date | Change |
|------|--------|
| 2026-10-10 | Staging compartment `mana-guruji-staging` created |
| 2026-10-10 | Staging Terraform module `staging_stack` + env; status doc created |
