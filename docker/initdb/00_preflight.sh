#!/bin/bash
set -euo pipefail
echo "[initdb 00] preflight: assets + vector extension"
for f in /delivery/01_*.dump /delivery/03_*.sql /delivery/04_*.sql /delivery/12_*.sql /delivery/14_*.sql /delivery/18_*.sql /delivery/19_*.sql /delivery/20_*.sql /delivery/21_*.sql /delivery/22_*.sql /delivery/38_*.sql /delivery/40_*.sql /delivery/41_*.sql /delivery/42_*.sql /delivery/43_*.sql /delivery/47_*.sql /delivery/49_*.sql /delivery/53_*.sql /delivery/54_*.sql /delivery/55_*.sql /delivery/56_*.sql /delivery/57_*.sql /delivery/58_*.sql /delivery/59_*.sql /delivery/61_*.sql; do
  [ -f "$f" ] || { echo "[initdb 00] MISSING $f"; exit 1; }
done
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'vector=' || extversion FROM pg_extension WHERE extname='vector';"
echo "[initdb 00] ok"