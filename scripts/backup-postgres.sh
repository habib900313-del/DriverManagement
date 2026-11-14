#!/usr/bin/env bash
# Consistent PostgreSQL backup of the primary database.
#
# The database stays online: pg_dump takes a transactionally consistent
# snapshot without stopping the application.
#
# Restore into a scratch database with:
#   createdb -h 127.0.0.1 -U driverapp drivermanagement_restore
#   psql -h 127.0.0.1 -U driverapp -d drivermanagement_restore \
#        -v ON_ERROR_STOP=1 -f backups/drivermanagement-pg-<stamp>.sql
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
PG_BIN="${PG_BIN:-/Library/PostgreSQL/18/bin}"
ENV_FILE="$PROJECT_DIR/.env.postgres"

DB_NAME="${DB_NAME:-drivermanagement}"
DB_USER="${DB_USER:-driverapp}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  DB_NAME="${DB_NAME:-drivermanagement}"
  DB_USER="${DB_USER:-driverapp}"
  DB_HOST="${DB_HOST:-127.0.0.1}"
  DB_PORT="${DB_PORT:-5432}"
fi

# the env file carries DB_PASSWORD; libpq expects PGPASSWORD
if [[ -z "${PGPASSWORD:-}" && -n "${DB_PASSWORD:-}" ]]; then
  PGPASSWORD="$DB_PASSWORD"
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "Error: PGPASSWORD (or DB_PASSWORD in $ENV_FILE) is required." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/drivermanagement-pg-$STAMP.sql"

export PGPASSWORD

"$PG_BIN/pg_dump" \
  --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
  --dbname="$DB_NAME" \
  --no-owner --no-privileges \
  --file="$TARGET"

echo "Backup written to: $TARGET"
echo "Restore with:"
echo "  createdb -h $DB_HOST -U $DB_USER drivermanagement_restore"
echo "  psql -h $DB_HOST -U $DB_USER -d drivermanagement_restore -v ON_ERROR_STOP=1 -f $TARGET"
