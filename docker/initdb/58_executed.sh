#!/bin/bash
set -euo pipefail
echo "[initdb 58] apply 37 (meal_plan.is_executed)"
# 显式文件名：37 号同时有 .md 说明，禁用 37_*.sql 通配（BUG-055 / issue #20）
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/37_meal_plan_is_executed_v1.2r3.sql"
echo "[initdb 58] ok"
