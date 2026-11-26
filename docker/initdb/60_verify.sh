#!/bin/bash
set -euo pipefail
# 显式文件名：禁止 /delivery/04_*.sql 这类通配（BUG-055 / issue #20）。
echo "[initdb 60] acceptance 04 + 22 + 43 + summary"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/04_数据库整体验收.sql"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/22_数据补充验收_v1.2r2.sql"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "/delivery/43_审核激活验收_v1.2r4.sql"
# 37 is_executed / 63 nutrition_tips 必须真实落在 app.meal_plan 上（缺列会让后端 400/500）。
meal_plan_cols=$(psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns WHERE table_schema='app' AND table_name='meal_plan' AND column_name IN ('is_executed','nutrition_tips');")
echo "[initdb 60] app.meal_plan cols: ${meal_plan_cols}"
case "$meal_plan_cols" in *is_executed*) ;; *) echo "[initdb 60] ASSERT FAIL: app.meal_plan.is_executed 缺失（37 未执行）"; exit 1 ;; esac
case "$meal_plan_cols" in *nutrition_tips*) ;; *) echo "[initdb 60] ASSERT FAIL: app.meal_plan.nutrition_tips 缺失（63 未执行）"; exit 1 ;; esac
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish=' || count(*) FROM core.dish WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'ingredient=' || count(*) FROM core.ingredient WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'fiber_calcium_dishes=' || count(*) FROM core.dish WHERE NOT is_deleted AND nutrition_snapshot ? 'dish_fiber_g' AND nutrition_snapshot ? 'dish_calcium_mg';"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'symptom_rows=' || count(*) || ' pending=' || count(*) FILTER (WHERE review_status='pending') || ' approved=' || count(*) FILTER (WHERE review_status='approved') || ' active=' || count(*) FILTER (WHERE is_active) FROM core.symptom_nutrient_map;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'condition_rules=' || count(*) || ' approved=' || count(*) FILTER (WHERE review_status='approved') || ' active=' || count(*) FILTER (WHERE is_active) FROM core.condition_nutrient_rule;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'production_rules=' || count(*) FROM app.v_production_condition_rules;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'review_activation=' || count(*) FROM audit.schema_migration WHERE migration_id IN ('2026-11-19-reverse-nutrition-activation','2026-11-19-condition-rule-review');"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'knowledge_total=' || count(*) FROM knowledge.knowledge_doc WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'backlog=' || count(*) FROM knowledge.v_embedding_backlog;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'condition_rows=' || count(*) FROM core.health_condition;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'migrations=' || count(*) FROM audit.schema_migration;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'diet_app_super=' || rolsuper FROM pg_roles WHERE rolname='diet_app';"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'server=' || version();"
echo "[initdb 60] done"
