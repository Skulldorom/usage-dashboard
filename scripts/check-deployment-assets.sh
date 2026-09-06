#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

require_text() {
  pattern=$1
  file=$2
  if ! grep -Fq -- "$pattern" "$file"; then
    echo "Expected '$pattern' in $file" >&2
    exit 1
  fi
}

# Keep documentation assets aligned with the executable container contract.
require_text 'EXPOSE 8000' backend/Dockerfile
require_text 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000' backend/Dockerfile
require_text 'EXPOSE 80' frontend/Dockerfile
require_text 'proxy_pass http://backend:8000/api/;' frontend/nginx.conf
require_text 'proxy_pass http://backend:8000/health;' frontend/nginx.conf
require_text 'ghcr.io/skulldorom/usage-dashboard-backend:' docker-compose.yml
require_text 'ghcr.io/skulldorom/usage-dashboard-frontend:' docker-compose.yml
require_text 'postgres:18-alpine' docker-compose.yml
require_text 'CUSTOM_HTTP_ALLOWED_HOSTS: ${CUSTOM_HTTP_ALLOWED_HOSTS:-}' docker-compose.yml
require_text 'ANALYTICS_HOURLY_RETENTION_DAYS: ${ANALYTICS_HOURLY_RETENTION_DAYS:-365}' docker-compose.yml

require_text 'ExecStart=/opt/usage-dashboard/backend/.venv/bin/alembic' deploy/systemd/usage-dashboard-migrate.service
require_text 'Requires=usage-dashboard-migrate.service' deploy/systemd/usage-dashboard-backend.service
require_text 'Restart=on-failure' deploy/systemd/usage-dashboard-backend.service
require_text 'proxy_pass http://127.0.0.1:8000/api/;' deploy/nginx/usage-dashboard.conf
require_text 'proxy_pass http://127.0.0.1:8000/health;' deploy/nginx/usage-dashboard.conf
require_text 'try_files $uri $uri/ /index.html;' deploy/nginx/usage-dashboard.conf

# systemd-analyze checks the unit grammar. Replace deployment-only paths and the
# distro PostgreSQL unit in temporary copies so verification is host-independent.
if command -v systemd-analyze >/dev/null 2>&1; then
  check_dir=$(mktemp -d)
  trap 'rm -rf "$check_dir"' EXIT HUP INT TERM
  for unit in deploy/systemd/*.service; do
    sed \
      -e '/^Requires=postgresql\.service$/d' \
      -e 's/postgresql\.service//g' \
      -e 's#^ExecStart=.*#ExecStart=/bin/true#' \
      "$unit" > "$check_dir/$(basename "$unit")"
  done
  systemd-analyze verify "$check_dir"/*.service
  rm -rf "$check_dir"
  trap - EXIT HUP INT TERM
fi

# Validate the shipped nginx grammar when Docker is available (as on GitHub's
# Ubuntu runner) without installing host packages.
if command -v docker >/dev/null 2>&1; then
  docker run --rm \
    -v "$repo_root/deploy/nginx/usage-dashboard.conf:/etc/nginx/conf.d/default.conf:ro" \
    nginx:1.31-alpine nginx -t
fi

echo 'Deployment asset checks passed.'
