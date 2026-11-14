#!/usr/bin/env bash
# Start the Vite development server (frontend) on 127.0.0.1:5173.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Error: frontend dependencies are not installed." >&2
  echo "Run: cd frontend && npm install" >&2
  exit 1
fi

cd "$FRONTEND_DIR"
exec npm run dev
