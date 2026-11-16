#!/bin/bash
set -euo pipefail
echo "[initdb 56] apply 20 (iron reference + fiber/calcium supplement)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/20_*.sql
echo "[initdb 56] ok"