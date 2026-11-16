#!/bin/bash
set -euo pipefail
echo "[initdb 30] apply 03 (app account + grants)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/03_*.sql
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'diet_app_super=' || rolsuper FROM pg_roles WHERE rolname='diet_app';"
echo "[initdb 30] ok"