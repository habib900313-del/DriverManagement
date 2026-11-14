#!/usr/bin/env bash
# Start backend and frontend together; Ctrl+C stops both.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$PROJECT_DIR/scripts/start-backend.sh" &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Give Django a moment before the browser-facing server comes up.
sleep 2
"$PROJECT_DIR/scripts/start-frontend.sh"
