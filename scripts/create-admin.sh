#!/usr/bin/env bash
# Create the single administrator account using Django's built-in auth.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
# Active environment (Python 3.14). Override with DM_VENV if needed.
VENV_DIR="${DM_VENV:-$BACKEND_DIR/.venv314}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Error: Python virtual environment not found at $VENV_DIR" >&2
  exit 1
fi

cd "$BACKEND_DIR"
exec "$VENV_DIR/bin/python" manage.py createsuperuser
