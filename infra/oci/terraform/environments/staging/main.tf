# stg-aio-1 — see infra/oci/fleet.launch.yaml environments.staging

module "staging_stack" {
  source = "../../modules/staging_stack"

  compartment_id        = var.compartment_id
  display_name_prefix   = var.display_name_prefix
  hostname              = "stg-aio-1"
  ssh_public_key        = var.ssh_public_key
  ssh_allowed_cidrs     = var.ssh_allowed_cidrs
  boot_volume_gb            = var.boot_volume_gb
  availability_domain_name  = var.availability_domain_name
}
