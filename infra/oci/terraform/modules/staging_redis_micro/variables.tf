variable "compartment_id" {
  type        = string
  description = "Staging compartment OCID."
}

variable "vcn_id" {
  type        = string
  description = "Existing staging VCN OCID (from staging_stack)."
}

variable "subnet_id" {
  type        = string
  description = "Subnet for the Redis host (same VCN as stg-aio-1)."
}

variable "display_name_prefix" {
  type        = string
  default     = "mana-guruji-stg"
}

variable "hostname" {
  type        = string
  default     = "stg-redis-1"
  description = "OCI display name / hostname label."
}

variable "ssh_public_key" {
  type        = string
  sensitive   = true
}

variable "ssh_allowed_cidrs" {
  type        = list(string)
  description = "SSH ingress (same policy as stg-aio-1)."
}

variable "redis_client_cidr" {
  type        = string
  default     = "10.60.1.0/24"
  description = "CIDR allowed to connect to Redis TCP/6379 (staging app subnet)."
}

variable "redis_image" {
  type        = string
  default     = "redis:7-alpine"
  description = "Docker image tag for Redis 7 (fleet.launch.yaml software.redis)."
}

variable "availability_domain_name" {
  type    = string
  default = null
}
