#!/bin/bash
set -euo pipefail
# 37 号目前只有说明文档（37_21号反向营养映射审核修订说明.md），没有对应的 .sql；
# meal_plan.is_executed 由后端迁移提供。没有 SQL 时直接跳过，避免 glob 不匹配导致 psql 报错。
echo "[initdb 58] apply 37 (meal_plan.is_executed) if present"
shopt -s nullglob
files=(/delivery/37_*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "[initdb 58] skip: no 37_*.sql in /delivery (37 is a doc, is_executed comes from backend migration)"
  exit 0
fi
for f in "${files[@]}"; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
echo "[initdb 58] ok"
