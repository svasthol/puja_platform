# Values aligned with infra/oci/fleet.launch.yaml environments.staging.hosts[stg-aio-1]

variable "compartment_id" {
  type        = string
  description = "OCI compartment OCID for staging resources."
}

variable "display_name_prefix" {
  type        = string
  default     = "mana-guruji-stg"
  description = "Prefix for VCN, subnet, and instance display names."
}

variable "hostname" {
  type        = string
  default     = "stg-aio-1"
  description = "Instance display name / hostname label (fleet.launch.yaml)."
}

variable "vcn_cidr" {
  type        = string
  default     = "10.60.0.0/16"
  description = "Staging VCN CIDR (isolated from planned prod 10.50.0.0/16)."
}

variable "subnet_cidr" {
  type        = string
  default     = "10.60.1.0/24"
  description = "Public subnet for SSH (fleet: assign_public_ip bastion_ssh)."
}

variable "shape" {
  type        = string
  default     = "VM.Standard.A1.Flex"
  description = "fleet.launch.yaml defaults.shape"
}

variable "ocpu_count" {
  type        = number
  default     = 1
  description = "fleet.launch.yaml staging stg-aio-1 ocpu"
}

variable "memory_gb" {
  type        = number
  default     = 6
  description = "fleet.launch.yaml staging stg-aio-1 memory_gb"
}

variable "boot_volume_gb" {
  type        = number
  default     = 50
  description = "fleet.launch.yaml staging boot_volume_gb"
}

variable "ssh_public_key" {
  type        = string
  description = "OpenSSH public key (single line) for opc user."
  sensitive   = true
}

variable "ssh_allowed_cidrs" {
  type        = list(string)
  description = "Ingress CIDRs for TCP/22 on the staging security list."
}

variable "developer_allowed_cidrs" {
  type        = list(string)
  default     = []
  description = "Laptop /32 for app ports (8000 API, 3000 admin, 6379 Redis). Postgres: SSH tunnel only."
}

variable "developer_tcp_ports" {
  type        = list(number)
  default     = [8000, 3000, 6379]
  description = "TCP ports opened to developer_allowed_cidrs. Do not expose 5432 — DB is localhost on VM."
}

variable "operating_system_version" {
  type        = string
  default     = "9"
  description = "Oracle Linux major version (aarch64 image filter)."
}

variable "availability_domain_name" {
  type        = string
  default     = null
  description = "Optional AD pin (multi-AD regions only). Null = first AD from oci_identity_availability_domains."
}
