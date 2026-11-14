#!/usr/bin/env bash
# Create a consistent SQLite backup without stopping the application.
# SQLite's .backup command is safe while the database is in use.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE="$PROJECT_DIR/backend/db.sqlite3"
BACKUP_DIR="$PROJECT_DIR/backups"

if [[ ! -f "$DATABASE" ]]; then
  echo "Error: database not found at $DATABASE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/db-$STAMP.sqlite3"

sqlite3 "$DATABASE" ".backup '$TARGET'"
echo "Backup written to: $TARGET"
