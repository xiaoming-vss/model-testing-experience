#!/usr/bin/env bash
# Verify locked dependencies and build the six application images.
# Usage: scripts/build_images.sh [control-plane|ai-worker|...]
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

all_apps=(control-plane ai-worker api-ui-worker integration-worker perf-worker studio)
selected=("$@")
if [[ ${#selected[@]} -eq 0 ]]; then
  selected=("${all_apps[@]}")
fi

for app in "${selected[@]}"; do
  if [[ " ${all_apps[*]} " != *" $app "* ]]; then
    echo "Unknown application: $app" >&2
    echo "Expected one of: ${all_apps[*]}" >&2
    exit 2
  fi
done

wants() {
  [[ " ${selected[*]} " == *" $1 "* ]]
}

for app in control-plane ai-worker api-ui-worker integration-worker perf-worker; do
  if wants "$app"; then
    command -v uv >/dev/null || {
      echo "uv is required for Python lockfile checks" >&2
      exit 1
    }
    (cd "apps/$app" && uv lock --check)
  fi
done

for app in ai-worker studio; do
  if wants "$app"; then
    command -v npm >/dev/null || {
      echo "npm is required for JavaScript lockfile checks" >&2
      exit 1
    }
    (cd "apps/$app" && npm ci --ignore-scripts --dry-run --no-audit --no-fund >/dev/null)
  fi
done

command -v docker >/dev/null || {
  echo "docker is required to build images" >&2
  exit 1
}

for app in "${selected[@]}"; do
  args=()
  if [[ "$app" == studio && -n "${VITE_API_BASE_URL:-}" ]]; then
    args+=(--build-arg "VITE_API_BASE_URL=${VITE_API_BASE_URL}")
  fi
  docker build "${args[@]}" -f "apps/$app/Dockerfile" -t "mtx/$app:ci" "apps/$app"
done
