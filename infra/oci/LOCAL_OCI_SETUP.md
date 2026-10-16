# Local OCI CLI + Terraform auth (Windows)

Your credentials live **only** on your machine under **`puja_platform/.oci/`** (gitignored).

| Path | Purpose |
|------|---------|
| `.oci/config` | Tenancy, user OCID, fingerprint, `key_file`, `region` |
| `.oci/keys/*.pem` | API private/public key pair |

Template for new machines: [`.oci/config.example`](../../.oci/config.example).

---

## Point CLI and Terraform at this config

Default OCI tools read `%USERPROFILE%\.oci\config`. This repo uses a **project-local** config instead.

**PowerShell (current session):**

```powershell
$env:OCI_CLI_CONFIG_FILE = "C:\OM\Guruji\mana_guruji\puja_platform\.oci\config"
```

**PowerShell (persist for your user — optional):**

```powershell
[System.Environment]::SetEnvironmentVariable(
  "OCI_CLI_CONFIG_FILE",
  "C:\OM\Guruji\mana_guruji\puja_platform\.oci\config",
  "User"
)
```

**Git Bash:**

```bash
export OCI_CLI_CONFIG_FILE="/c/OM/Guruji/mana_guruji/puja_platform/.oci/config"
```

Terraform **`oracle/oci` v6** does not support `config_file_path` or `OCI_CLI_CONFIG_FILE`. Before `terraform plan/apply`, dot-source **`Set-OciConfig.ps1`** — it sets `TF_VAR_tenancy_ocid`, `user_ocid`, `fingerprint`, `private_key_path` (and passphrase if needed) from `.oci/config`.

---

## Smoke test (after setting `OCI_CLI_CONFIG_FILE`)

```powershell
oci iam region list --output table
oci os ns get
```

Expect `ap-hyderabad-1` in config and a namespace from `os ns get`.

---

## Security

- **Never** commit `.oci/config` or `.oci/keys/` (see root `.gitignore`).
- Do not put API passphrases in chat, tickets, or CI logs.
- GitHub Actions will use **different** secrets (API key in GitHub Secrets), not this folder.

---

## Next step toward Terraform

When `infra/oci/terraform/` is scaffolded:

```powershell
cd C:\OM\Guruji\mana_guruji\puja_platform\infra\oci\terraform\environments\staging
$env:OCI_CLI_CONFIG_FILE = "C:\OM\Guruji\mana_guruji\puja_platform\.oci\config"
terraform init
terraform plan
```

Fleet sizes: [`spec/plans/OCI_COMPUTE_FLEET.md`](../../spec/plans/OCI_COMPUTE_FLEET.md) · [`fleet.launch.yaml`](./fleet.launch.yaml).
