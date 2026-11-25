#!/bin/bash
set -euo pipefail
# 41 号有两份 SQL，41_*.sql 一次传给 psql 只执行第一个，反向营养激活会被静默跳过（43 随即报缺迁移记录）。
echo "[initdb 59] apply 41 (reverse nutrition review & activation) + 42 (condition rule review) + 43 (acceptance)"
shopt -s nullglob
files=(/delivery/41_反向*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "[initdb 59] MISSING /delivery/41_反向*.sql"; exit 1
fi
for f in "${files[@]}"; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/42_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/43_*.sql
echo "[initdb 59] ok"
