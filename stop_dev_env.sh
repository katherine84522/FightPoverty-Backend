#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="./docker-compose.dev.yml"

case "${1:-down}" in
  down)
    echo "🛑 Stopping development containers (keeping volumes)..."
    docker compose -f "$COMPOSE_FILE" down
    ;;
  clean)
    echo "🔥 Stopping containers and removing volumes (Redis data will be lost)..."
    docker compose -f "$COMPOSE_FILE" down -v
    ;;
  *)
    echo "Usage:"
    echo "  $0            # docker compose down"
    echo "  $0 clean      # docker compose down -v (remove volumes)"
    exit 1
    ;;
esac

echo "✅ Done."
