#!/bin/bash
set -euo pipefail
echo "[initdb 00] preflight: assets + vector extension"
for f in /delivery/01_*.dump /delivery/03_*.sql /delivery/04_*.sql /delivery/12_*.sql /delivery/14_*.sql /delivery/18_*.sql /delivery/19_*.sql /delivery/20_*.sql /delivery/21_*.sql /delivery/22_*.sql /delivery/41_*.sql /delivery/42_*.sql /delivery/43_*.sql; do
  [ -f "$f" ] || { echo "[initdb 00] MISSING $f"; exit 1; }
done
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'vector=' || extversion FROM pg_extension WHERE extname='vector';"
echo "[initdb 00] ok"