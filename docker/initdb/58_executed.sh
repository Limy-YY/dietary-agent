#!/bin/bash
set -euo pipefail
echo "[initdb 58] apply 37 (meal_plan.is_executed)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/37_*.sql
echo "[initdb 58] ok"
