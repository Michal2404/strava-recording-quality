#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR_DEFAULT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APP_DIR="${1:-${APP_DIR_DEFAULT}}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/infra/ec2/.env.ec2}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  echo "Create it from ${APP_DIR}/infra/ec2/.env.ec2.example" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found. Run infra/ec2/bootstrap_host.sh first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

cd "${APP_DIR}"

docker compose --env-file "${ENV_FILE}" -f infra/docker-compose.yml up -d --build api db redis
docker compose --env-file "${ENV_FILE}" -f infra/docker-compose.yml exec -T api alembic upgrade head

API_PORT="${HOST_API_PORT:-8000}"
curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null

echo "Deploy completed. Health endpoint responds on http://127.0.0.1:${API_PORT}/health"
