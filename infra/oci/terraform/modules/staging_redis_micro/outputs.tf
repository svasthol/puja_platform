output "instance_id" {
  value = oci_core_instance.redis.id
}

output "private_ip" {
  value = oci_core_instance.redis.private_ip
}

output "public_ip" {
  value = oci_core_instance.redis.public_ip
}

output "redis_port" {
  value       = 6379
  description = "Redis TCP port (Docker publish on micro)."
}

# Logical DB 0 — app cache / presence (see REDIS_DB_CACHE in api.env)
output "redis_url" {
  value       = "redis://${oci_core_instance.redis.private_ip}:6379/0"
  description = "Primary REDIS_URL on stg-aio-1 (private IP, DB 0 puja cache)."
}

output "redis_url_celery" {
  value       = "redis://${oci_core_instance.redis.private_ip}:6379/1"
  description = "Celery broker+result (DB 1) — wire in phase 2 when celery URLs are split."
}

output "redis_url_public" {
  value       = "redis://${oci_core_instance.redis.public_ip}:6379/0"
  description = "Public endpoint — only if redis_extra_client_cidrs allows your IP; prefer private URL."
}
