#!/bin/bash
set -euo pipefail
echo "[initdb 40] apply 18 (health conditions)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/18_*.sql
echo "[initdb 40] ok"