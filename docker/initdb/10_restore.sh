#!/bin/bash
set -euo pipefail
echo "[initdb 10] restore 01 dump (v1.2r2 merged)"
pg_restore --no-owner --no-privileges --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" /delivery/01_*.dump
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish=' || count(*) FROM core.dish;"
echo "[initdb 10] ok"
