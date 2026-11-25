#!/bin/bash
set -euo pipefail
echo "[initdb 59] apply 41 (reverse nutrition review & activation) + 42 (condition rule review) + 43 (acceptance)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/41_反向营养映射审核激活_v1.2r4.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/42_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/43_*.sql
echo "[initdb 59] ok"
