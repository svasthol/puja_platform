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
