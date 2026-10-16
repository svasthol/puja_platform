# Source before oci CLI and terraform in this repo (project-local .oci/config).
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Config = Join-Path $RepoRoot ".oci\config"
if (-not (Test-Path $Config)) {
    Write-Error "Missing $Config - copy from .oci/config.example and add keys under .oci/keys/"
    exit 1
}

function Read-OciConfigProfile {
    param(
        [string]$Path,
        [string]$ProfileName = "DEFAULT"
    )
    $result = @{}
    $active = $false
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#") -or $trimmed.StartsWith(";")) {
            continue
        }
        if ($trimmed -match '^\[(.+)\]$') {
            $active = ($matches[1] -eq $ProfileName)
            continue
        }
        if (-not $active) {
            continue
        }
        if ($trimmed -match '^([^=]+)=(.*)$') {
            $result[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
    return $result
}

$env:OCI_CLI_CONFIG_FILE = $Config
Write-Host ('OCI_CLI_CONFIG_FILE=' + $env:OCI_CLI_CONFIG_FILE)

# oracle/oci provider v6: no config_file_path; use API key fields (or ~/.oci/config only).
$profile = Read-OciConfigProfile -Path $Config -ProfileName "DEFAULT"
$required = @("tenancy", "user", "fingerprint", "key_file")
foreach ($key in $required) {
    if (-not $profile.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($profile[$key])) {
        Write-Error "OCI config missing '$key' in [DEFAULT] profile."
        exit 1
    }
}

$keyPath = $profile["key_file"]
if (-not (Test-Path -LiteralPath $keyPath)) {
    Write-Error "Private key not found at key_file path from config."
    exit 1
}

$env:TF_VAR_tenancy_ocid = $profile["tenancy"]
$env:TF_VAR_user_ocid = $profile["user"]
$env:TF_VAR_fingerprint = $profile["fingerprint"]
$env:TF_VAR_private_key_path = (Resolve-Path -LiteralPath $keyPath).Path
if ($profile.ContainsKey("pass_phrase") -and -not [string]::IsNullOrWhiteSpace($profile["pass_phrase"])) {
    $env:TF_VAR_private_key_password = $profile["pass_phrase"]
} else {
    Remove-Item Env:TF_VAR_private_key_password -ErrorAction SilentlyContinue
}

if ($profile.ContainsKey("region") -and -not [string]::IsNullOrWhiteSpace($profile["region"])) {
    $env:TF_VAR_region = $profile["region"]
}

Write-Host "Terraform auth: TF_VAR_tenancy_ocid / user_ocid / fingerprint / private_key_path set from .oci/config"
