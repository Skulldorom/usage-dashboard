#!/bin/sh
# Build frontend and matching backend metadata from a clean release checkout.
set -eu
cd "$(dirname "$0")/.."
version=unknown
if test -z "$(git status --porcelain --untracked-files=no)"; then
  tag=$(git describe --tags --exact-match HEAD 2>/dev/null || true)
  if printf '%s\n' "$tag" | grep -Eq '^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'; then
    version=$tag
  fi
fi
(cd frontend && VITE_APP_VERSION="$version" npm run build)
printf 'APP_VERSION=%s\n' "$version" > deploy/version.env
printf 'Built application version: %s\n' "$version"
