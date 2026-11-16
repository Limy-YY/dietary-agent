#!/bin/bash
set -euo pipefail
echo "[initdb 55] apply 19 (knowledge topics 26 -> 43)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/19_*.sql
echo "[initdb 55] ok"