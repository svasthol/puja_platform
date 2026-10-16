output "vcn_id" {
  description = "Staging VCN OCID."
  value       = oci_core_vcn.staging.id
}

output "subnet_id" {
  description = "Staging public subnet OCID."
  value       = oci_core_subnet.public.id
}

output "instance_id" {
  description = "stg-aio-1 compute instance OCID."
  value       = oci_core_instance.stg_aio.id
}

output "instance_private_ip" {
  description = "Private IP of the primary VNIC."
  value       = oci_core_instance.stg_aio.private_ip
}

output "instance_public_ip" {
  description = "Public IP for SSH (opc)."
  value       = oci_core_instance.stg_aio.public_ip
}

output "ssh_command" {
  description = "Example SSH after apply."
  value       = "ssh opc@${oci_core_instance.stg_aio.public_ip}"
}

output "availability_domain" {
  value = local.ad_name
}

output "image_id" {
  description = "Oracle Linux aarch64 image used at apply time."
  value       = local.image_id
}
