# Staging environment — `stg-aio-1`

| Field | Value (SSOT) |
|-------|----------------|
| Hostname | `stg-aio-1` |
| Shape | `VM.Standard.A1.Flex` |
| OCPU / RAM | 1 / 6 GB |
| Boot disk | 50 GB |
| OS | Oracle Linux 9 aarch64 |
| Network | Dedicated staging VCN `10.60.0.0/16`, public subnet for SSH |

## Apply

1. **Required:** `. C:\OM\Guruji\mana_guruji\puja_platform\infra\oci\scripts\Set-OciConfig.ps1` (sets CLI + Terraform `TF_VAR_*` auth)
2. `copy terraform.tfvars.example terraform.tfvars` and edit
3. `terraform init` → `plan` → `apply`  
   **A1 out of capacity:** `..\..\..\scripts\Retry-StagingTerraformApply.ps1 -IntervalMinutes 10` (one window, laptop awake)
4. Update [`spec/plans/OCI_INFRA_STATUS.md`](../../../../spec/plans/OCI_INFRA_STATUS.md) and fleet inventory in [`OCI_COMPUTE_FLEET.md`](../../../../spec/plans/OCI_COMPUTE_FLEET.md)

## Post-apply (manual)

Oracle Linux 9: install PG16+PostGIS, Redis 7, Python 3.12, clone repo, OL9 pip gate — see [`OCI_PROD_MANUAL_RUNBOOK.md`](../../../../spec/plans/OCI_PROD_MANUAL_RUNBOOK.md) (same stack, single host).
