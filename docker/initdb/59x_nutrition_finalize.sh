#!/bin/bash
set -euo pipefail
# 营养与档案收口：40 确定不含微量补零（盐/油/糖/菌藻）→ 55 补维生素A（豆浆/白菜薹/生菜）
# → 56 补维生素C（豆浆/鸡腿）→ 57 统一维生素A为 RAE 口径 → 58 白米饭 65g 生米 → 59 档案瘦身。
# 前置：59w 已把 222 道落库（55/56/58 依赖 45 带进的白菜薹/生菜/豆浆/鸡腿与 DISH-121 白米饭）。
# 六个脚本均幂等，可重复执行。
echo "[initdb 59x] apply 40 + 55 + 56 + 57 + 58 + 59 (micro-nutrients & profile slimming)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/40_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/55_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/56_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/57_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/58_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/59_*.sql
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish_121_rice_g=' || string_agg(amount_g::text, ',') FROM core.dish_ingredient di JOIN core.ingredient i USING (ingredient_id) WHERE di.dish_id='DISH-121' AND i.food_id='CN-280';"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'vit_a_null_ing=' || count(*) FROM core.ingredient WHERE NOT is_deleted AND (micro_nutrients->>'vitamin_a_ug') IS NULL;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'vit_c_null_ing=' || count(*) FROM core.ingredient WHERE NOT is_deleted AND (micro_nutrients->>'vitamin_c_mg') IS NULL;"
echo "[initdb 59x] ok"
