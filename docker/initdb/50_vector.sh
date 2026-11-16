#!/bin/bash
set -euo pipefail
echo "[initdb 50] apply 14 (RAG vector structure)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/14_*.sql
echo "[initdb 50] ok"