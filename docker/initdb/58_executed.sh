#!/bin/bash
set -euo pipefail
# 37_meal_plan_is_executed_v1.2r3.sql 提供 meal_plan.is_executed 列（v1.2r3，后端无对应迁移）。
# nullglob 兜底：万一交付包漏了该文件则跳过（00 预检应已拦住），避免 glob 不匹配导致 psql 报错。
echo "[initdb 58] apply 37 (meal_plan.is_executed) if present"
shopt -s nullglob
files=(/delivery/37_*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "[initdb 58] skip: no 37_*.sql in /delivery (is_executed migration missing — should be caught by preflight 00)"
  exit 0
fi
for f in "${files[@]}"; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
echo "[initdb 58] ok"
