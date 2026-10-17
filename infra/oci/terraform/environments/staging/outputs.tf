output "stg_aio_instance_id" {
  value = module.staging_stack.instance_id
}

output "stg_aio_public_ip" {
  value = module.staging_stack.instance_public_ip
}

output "stg_aio_private_ip" {
  value = module.staging_stack.instance_private_ip
}

output "ssh_command" {
  value = module.staging_stack.ssh_command
}

output "vcn_id" {
  value = module.staging_stack.vcn_id
}

output "subnet_id" {
  value = module.staging_stack.subnet_id
}

output "stg_redis_private_ip" {
  value       = try(module.staging_redis_micro[0].private_ip, null)
  description = "Set REDIS_URL on stg-aio-1 when enable_staging_redis_micro is true."
}

output "stg_redis_url" {
  value = try(module.staging_redis_micro[0].redis_url, null)
}

output "stg_redis_public_ip" {
  value       = try(module.staging_redis_micro[0].public_ip, null)
  description = "E2 Micro public IP (SSH + optional external Redis if NSG allows)."
}

output "stg_redis_url_celery" {
  value = try(module.staging_redis_micro[0].redis_url_celery, null)
}

output "stg_redis_url_public" {
  value       = try(module.staging_redis_micro[0].redis_url_public, null)
  description = "Use only when redis_extra_client_cidrs includes your IP."
}
