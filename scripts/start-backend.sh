#!/usr/bin/env bash
# Start the Django backend on the loopback interface only.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
# Active environment (Python 3.14). Override with DM_VENV if needed.
VENV_DIR="${DM_VENV:-$BACKEND_DIR/.venv314}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Error: Python virtual environment not found at $VENV_DIR" >&2
  echo "Create it with: /usr/local/bin/python3.14 -m venv backend/.venv314" >&2
  exit 1
fi

cd "$BACKEND_DIR"
exec "$VENV_DIR/bin/python" manage.py runserver 127.0.0.1:8000
