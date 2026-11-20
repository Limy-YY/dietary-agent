#!/bin/bash
set -euo pipefail
echo "[initdb 59] apply 41 (verified RAG source URLs)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/41_*.sql
echo "[initdb 59] ok"
