#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-hlstatsx_proxy_e2e}

cd "$SCRIPT_DIR"
docker compose up -d
