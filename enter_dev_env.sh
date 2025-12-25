#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="./docker-compose.dev.yml"

case "${1:-up}" in
  up)
    docker compose -f "$COMPOSE_FILE" up -d
    echo "✅ Dev env is up."
    echo "   Frontend: http://localhost:5173"
    echo "   Backend:  http://localhost:3001/health"
    ;;
  build)
    docker compose -f "$COMPOSE_FILE" up -d --build
    echo "✅ Dev env is up (rebuilt)."
    ;;
  sh)
    # default enter backend
    CID="$(docker compose -f "$COMPOSE_FILE" ps -q backend)"
    docker exec -it "$CID" sh
    ;;
  sh-frontend)
    CID="$(docker compose -f "$COMPOSE_FILE" ps -q frontend)"
    docker exec -it "$CID" sh
    ;;
  sh-redis)
    CID="$(docker compose -f "$COMPOSE_FILE" ps -q redis)"
    docker exec -it "$CID" sh
    ;;
  seed)
    CID="$(docker compose -f "$COMPOSE_FILE" ps -q backend)"
    docker exec -it "$CID" python seed_test_users.py
    ;;
  down)
    docker compose -f "$COMPOSE_FILE" down
    ;;
  *)
    echo "Usage:"
    echo "  $0 up|build|sh|sh-frontend|sh-redis|seed|down"
    exit 1
    ;;
esac
