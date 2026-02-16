#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (example: sudo bash infra/ec2/bootstrap_host.sh)." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  docker.io \
  docker-compose-plugin \
  git \
  nginx \
  certbot \
  python3-certbot-nginx

systemctl enable --now docker
systemctl enable --now nginx

if [[ -n "${SUDO_USER:-}" ]]; then
  usermod -aG docker "${SUDO_USER}" || true
fi

echo "Bootstrap complete."
echo "If your user was added to the docker group, log out and log in again before deploy."
