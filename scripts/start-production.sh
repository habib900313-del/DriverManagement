#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="${DM_VENV:-$BACKEND_DIR/.venv}"

if [[ ! -x "$VENV_DIR/bin/gunicorn" ]]; then
  echo "Error: Gunicorn was not found at $VENV_DIR/bin/gunicorn" >&2
  echo "Create the production virtual environment and install backend/requirements.txt." >&2
  exit 1
fi

export DJANGO_SETTINGS_MODULE="config.production_settings"
cd "$BACKEND_DIR"
exec "$VENV_DIR/bin/gunicorn" \
  --config "$BACKEND_DIR/config/gunicorn.conf.py" \
  --chdir "$BACKEND_DIR" \
  config.wsgi:application
