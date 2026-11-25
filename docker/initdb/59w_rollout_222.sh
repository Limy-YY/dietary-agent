#!/bin/bash
set -euo pipefail
# 222 规模落库：47 配餐结构 dish_meta 白名单 → 49 烤/空气炸 + 坚果 → 53 水果家常菜 13 道
# → 54 混合坚果 → 61 做法步骤补录。
# 前置：59v 已把基线补到 213（170 基础 + 43 少盐变体）；47 必须在 49/53/54 之前，61 必须在 54 之后。
# 五个脚本均幂等，可反复重跑。
echo "[initdb 59w] apply 47 + 49 + 53 + 54 + 61 (rollout to 222 dishes)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/47_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/49_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/53_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/54_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/61_*.sql
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_total=' || count(*) FROM core.dish WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_nLS=' || count(*) FROM core.dish WHERE dish_id NOT LIKE '%-LS' AND NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_LS=' || count(*) FROM core.dish WHERE dish_id LIKE '%-LS' AND NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_steps=' || count(*) FROM core.dish WHERE NOT is_deleted AND steps IS NOT NULL AND cardinality(steps) > 0;"
echo "[initdb 59w] ok"
