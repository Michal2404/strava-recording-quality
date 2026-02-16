#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (example: sudo bash infra/ec2/install_systemd_service.sh /opt/strava-recording-quality)." >&2
  exit 1
fi

APP_DIR="${1:-/opt/strava-recording-quality}"
ENV_FILE="${2:-${APP_DIR}/infra/ec2/.env.ec2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/systemd/srq-stack.service.template"
TARGET_FILE="/etc/systemd/system/srq-stack.service"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory not found: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Warning: env file not found: ${ENV_FILE}" >&2
fi

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "Missing template: ${TEMPLATE_FILE}" >&2
  exit 1
fi

sed \
  -e "s|__APP_DIR__|${APP_DIR}|g" \
  -e "s|__ENV_FILE__|${ENV_FILE}|g" \
  "${TEMPLATE_FILE}" > "${TARGET_FILE}"

systemctl daemon-reload
systemctl enable srq-stack.service
systemctl restart srq-stack.service

echo "Installed and started srq-stack.service"
echo "Check status with: systemctl status srq-stack.service"
