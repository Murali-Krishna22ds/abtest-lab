#!/usr/bin/env bash
# Build the UI, start the API (which serves it), run the browser tests, and shut everything down.
# Usage: scripts/e2e.sh [screenshot_dir]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
PORT="${PORT:-8765}"
cd "$ROOT/frontend" && npm run build --silent
cd "$ROOT/backend"
"$PY" -m uvicorn app.main:app --port "$PORT" --log-level warning &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 1; done
cd "$ROOT/frontend"
BASE_URL="http://127.0.0.1:$PORT" SHOTS="${1:-}" node e2e/smoke.mjs
