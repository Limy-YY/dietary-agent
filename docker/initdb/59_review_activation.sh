#!/bin/bash
set -euo pipefail
# 显式文件名：41 号有两个文件（RAG 来源链接 / 反向营养激活），
# psql -f /delivery/41_*.sql 只会执行第一个、其余静默丢弃（BUG-055 / issue #20）。
echo "[initdb 59] apply 41 (reverse nutrition review & activation) + 42 (condition rule review) + 43 (acceptance)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/41_反向营养映射审核激活_v1.2r4.sql"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/42_疾病规则口径审核_v1.2r4.sql"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/43_审核激活验收_v1.2r4.sql"
echo "[initdb 59] ok"
