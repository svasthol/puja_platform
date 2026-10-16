# OCI compartments — Mana Guruji

**Rule:** Create a **dedicated compartment per environment** before Terraform. Do **not** put staging and production in the tenancy root.

Parent is always the **tenancy OCID** (same for both commands below). Region for resources: **`ap-hyderabad-1`**.

---

## Staging — `mana-guruji-staging`

**Status:** Created (2026-10-10).

```bash
oci iam compartment create \
  --compartment-id <TENANCY_OCID> \
  --name mana-guruji-staging \
  --description "Staging environment for Mana Guruji"
```

**Resolve OCID for `terraform.tfvars`:**

```bash
oci iam compartment list --compartment-id-in-subtree true \
  --name mana-guruji-staging --query "data[0].id" --raw-output
```

Use that value as `compartment_id` in  
`infra/oci/terraform/environments/staging/terraform.tfvars`.

---

## Production — `mana-guruji-production` (before prod Terraform)

**Status:** Not created yet — repeat the same pattern **before** `environments/production` apply.

```bash
oci iam compartment create \
  --compartment-id <TENANCY_OCID> \
  --name mana-guruji-production \
  --description "Production environment for Mana Guruji"
```

Then:

1. Record prod compartment OCID in [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md).
2. Apply IAM policies so your deploy user/API key can manage resources **in that compartment only** (least privilege).
3. Use prod compartment OCID in future `terraform.tfvars` for production (separate state file).

---

## Console alternative

OCI Console → **Identity & Security** → **Compartments** → **Create compartment** (same names and descriptions).

---

## Tracking

| Compartment | Name | Terraform env | Status |
|-------------|------|---------------|--------|
| Staging | `mana-guruji-staging` | `infra/oci/terraform/environments/staging` | Created |
| Production | `mana-guruji-production` | *planned* `environments/production` | Pending |

See also [`OCI_INFRA_STATUS.md`](./OCI_INFRA_STATUS.md).
