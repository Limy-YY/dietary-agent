#!/bin/bash
set -euo pipefail
echo "[initdb 57] apply 21 (reverse nutrition mapping: 13 reviewed rows, pending)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/21_*.sql
echo "[initdb 57] ok"