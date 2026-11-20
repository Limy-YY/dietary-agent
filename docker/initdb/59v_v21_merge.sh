#!/bin/bash
set -euo pipefail
# 213 基线补齐：39 过敏原复核 → 45 v21 50 道合入 → 44 新食材落定 → 46 43 条少盐变体
# 前置：10 步已还原 01 备份（120 道基线），41/42/43 已执行。四个脚本均幂等。
echo "[initdb 59v] apply 39 (allergen review) + 45 (v21 50 dishes) + 44 (new ingredient settlement) + 46 (43 low-salt variants)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/39_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/45_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/44_博淇合并食材过敏原落定_v1.2r4.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/46_*.sql
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_total=' || count(*) FROM core.dish WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_nLS=' || count(*) FROM core.dish WHERE dish_id NOT LIKE '%-LS' AND NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_LS=' || count(*) FROM core.dish WHERE dish_id LIKE '%-LS' AND NOT is_deleted;"
echo "[initdb 59v] ok"
