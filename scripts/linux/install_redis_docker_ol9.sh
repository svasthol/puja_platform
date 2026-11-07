#!/usr/bin/env bash
# One-time repair on stg-redis-1 if cloud-init did not install Docker/Redis.
# Run on the micro: sed -i 's/\r$//' install_redis_docker_ol9.sh  # if copied from Windows
set -euo pipefail

REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"

dnf -y install dnf-plugins-core curl
if [[ ! -f /etc/yum.repos.d/docker-ce.repo ]]; then
  dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
fi
dnf -y install docker-ce docker-ce-cli containerd.io
systemctl enable --now docker
usermod -aG docker opc || true

docker pull "$REDIS_IMAGE"
docker rm -f mana-guruji-redis 2>/dev/null || true
docker run -d --name mana-guruji-redis --restart unless-stopped \
  -p 0.0.0.0:6379:6379 "$REDIS_IMAGE" \
  redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru

docker ps
redis-cli -h 127.0.0.1 ping
echo "install_redis_docker_ol9: OK"
