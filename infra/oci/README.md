# OCI infrastructure (IaC home)

**Compute SSOT:** [`spec/plans/OCI_COMPUTE_FLEET.md`](../../spec/plans/OCI_COMPUTE_FLEET.md)

| File | Status |
|------|--------|
| [`fleet.launch.yaml`](./fleet.launch.yaml) | **Chosen** — Option B (corrected), 5-node + staging |
| [`fleet.alternative-9vm.yaml`](./fleet.alternative-9vm.yaml) | **Not chosen** — reference only |
| [`terraform/`](./terraform/) | **Staging live** — `environments/staging`; prod planned |
| `ansible/` | Planned — host groups = `production.hosts[].hostname` |

When adding Terraform or Ansible, read `fleet.launch.yaml` first; do not duplicate OCPU/RAM/disk in HCL without a generator or comment linking to this file.

**Local API auth (Windows):** [`LOCAL_OCI_SETUP.md`](./LOCAL_OCI_SETUP.md) — project `.oci/` is gitignored; use `scripts/Set-OciConfig.ps1` before `oci` / `terraform`.
