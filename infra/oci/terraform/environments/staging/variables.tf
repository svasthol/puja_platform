variable "region" {
  type        = string
  default     = "ap-hyderabad-1"
  description = "OCI region (fleet.launch.yaml region)."
}

# Set via . Set-OciConfig.ps1 (exports TF_VAR_*) or in terraform.tfvars
variable "tenancy_ocid" {
  type        = string
  description = "Tenancy OCID (from .oci/config or Console)."
}

variable "user_ocid" {
  type        = string
  description = "User OCID (from .oci/config)."
}

variable "fingerprint" {
  type        = string
  description = "API key fingerprint (from .oci/config)."
}

variable "private_key_path" {
  type        = string
  description = "Path to API private key PEM (from .oci/config key_file)."
}

variable "private_key_password" {
  type        = string
  default     = null
  sensitive   = true
  description = "PEM passphrase if key_file is encrypted (pass_phrase in .oci/config)."
}

variable "compartment_id" {
  type        = string
  description = "Staging compartment OCID."
}

variable "ssh_public_key" {
  type        = string
  description = "OpenSSH public key for opc (contents of *.pub file)."
  sensitive   = true
}

variable "ssh_allowed_cidrs" {
  type        = list(string)
  description = "Your public IP as /32 recommended; avoid 0.0.0.0/0 in production-like staging."
}

variable "developer_allowed_cidrs" {
  type        = list(string)
  default     = []
  description = "Auto-updated by scripts/db_dev_staging_parity.py (developer.auto.tfvars.json)."
}

variable "developer_tcp_ports" {
  type        = list(number)
  default     = [8000, 3000, 6379]
  description = "App ports from laptop; Postgres via ssh -L 15432:127.0.0.1:5432."
}

variable "display_name_prefix" {
  type    = string
  default = "mana-guruji-stg"
}

variable "boot_volume_gb" {
  type        = number
  default     = 50
  description = "Instance boot volume size (fleet SSOT; OL9 image minimum 50 GB on OCI)."
}

variable "availability_domain_name" {
  type        = string
  default     = null
  description = "Optional AD pin (multi-AD regions only). ap-hyderabad-1 has a single AD; null uses aeXz:AP-HYDERABAD-1-AD-1."
}

variable "enable_staging_redis_micro" {
  type        = bool
  default     = false
  description = "If true, provision Always Free VM.Standard.E2.1.Micro (stg-redis-1) with Docker Redis 7 in the staging VCN."
}

variable "redis_extra_client_cidrs" {
  type        = list(string)
  default     = []
  description = "Optional: allow TCP/6379 from these CIDRs (e.g. laptop /32). Empty = only staging app subnet."
}
