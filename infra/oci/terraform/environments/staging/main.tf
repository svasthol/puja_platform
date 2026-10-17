# stg-aio-1 — see infra/oci/fleet.launch.yaml environments.staging

module "staging_stack" {
  source = "../../modules/staging_stack"

  compartment_id           = var.compartment_id
  display_name_prefix      = var.display_name_prefix
  hostname                 = "stg-aio-1"
  ssh_public_key           = var.ssh_public_key
  ssh_allowed_cidrs        = var.ssh_allowed_cidrs
  boot_volume_gb           = var.boot_volume_gb
  availability_domain_name = var.availability_domain_name
}

module "staging_redis_micro" {
  count  = var.enable_staging_redis_micro ? 1 : 0
  source = "../../modules/staging_redis_micro"

  compartment_id           = var.compartment_id
  vcn_id                     = module.staging_stack.vcn_id
  subnet_id                  = module.staging_stack.subnet_id
  display_name_prefix        = var.display_name_prefix
  ssh_public_key             = var.ssh_public_key
  ssh_allowed_cidrs          = var.ssh_allowed_cidrs
  availability_domain_name   = var.availability_domain_name
  redis_client_cidr          = "10.60.1.0/24"
  redis_extra_client_cidrs   = var.redis_extra_client_cidrs
}
