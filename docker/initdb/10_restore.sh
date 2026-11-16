#!/bin/bash
set -euo pipefail
echo "[initdb 10] restore 01 dump"
pg_restore --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /delivery/01_*.dump
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish=' || count(*) FROM core.dish;"
echo "[initdb 10] ok"