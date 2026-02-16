#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (example: sudo bash infra/ec2/setup_nginx_tls.sh api.example.com you@example.com)." >&2
  exit 1
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <domain> <letsencrypt_email>" >&2
  exit 1
fi

DOMAIN="$1"
EMAIL="$2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/nginx/srq-api.conf.template"
TARGET_FILE="/etc/nginx/sites-available/srq-api.conf"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "Missing template: ${TEMPLATE_FILE}" >&2
  exit 1
fi

sed "s/__DOMAIN__/${DOMAIN}/g" "${TEMPLATE_FILE}" > "${TARGET_FILE}"
ln -sfn "${TARGET_FILE}" /etc/nginx/sites-enabled/srq-api.conf
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx

certbot --nginx \
  --non-interactive \
  --agree-tos \
  --redirect \
  --email "${EMAIL}" \
  -d "${DOMAIN}"

systemctl reload nginx

echo "Nginx + TLS configured for https://${DOMAIN}"
