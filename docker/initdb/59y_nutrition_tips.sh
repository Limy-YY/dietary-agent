#!/bin/bash
set -euo pipefail
# B2 营养提示落库（63）：仅给 app.meal_plan 增列 nutrition_tips，幂等。
# 位置：59x 之后、60 之前。后端起效依赖本列，缺列会让配餐生成 400、方案查询 500。
# 显式文件名，不用 /delivery/63_*.sql 通配（BUG-055 / issue #20 的教训）。
echo "[initdb 59y] apply 63 (app.meal_plan.nutrition_tips)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/63_营养提示落库_v1.2r5.sql"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'nutrition_tips_col=' || count(*) FROM information_schema.columns WHERE table_schema='app' AND table_name='meal_plan' AND column_name='nutrition_tips';"
echo "[initdb 59y] ok"
