#!/bin/bash
set -euo pipefail
echo "[initdb 20] apply 12 (v1.2 -> v1.2r1)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/12_*.sql
echo "[initdb 20] ok"