output "instance_id" {
  value = oci_core_instance.redis.id
}

output "private_ip" {
  value = oci_core_instance.redis.private_ip
}

output "public_ip" {
  value = oci_core_instance.redis.public_ip
}

output "redis_url" {
  value       = "redis://${oci_core_instance.redis.private_ip}:6379/0"
  description = "Set REDIS_URL in /etc/mana-guruji/api.env on stg-aio-1."
}
