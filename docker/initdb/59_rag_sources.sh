#!/bin/bash
set -euo pipefail
# 41 号有两份 SQL（RAG 来源链接 / 反向营养映射审核激活），用 41_*.sql 一次传给 psql 只会执行第一个，
# 第二个会被当成多余参数静默忽略。这里逐个显式执行。
echo "[initdb 59] apply 41 (verified RAG source URLs)"
shopt -s nullglob
files=(/delivery/41_RAG*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "[initdb 59] MISSING /delivery/41_RAG*.sql"; exit 1
fi
for f in "${files[@]}"; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
echo "[initdb 59] ok"
