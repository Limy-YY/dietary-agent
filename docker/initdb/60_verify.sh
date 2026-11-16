#!/bin/bash
set -euo pipefail
echo "[initdb 60] acceptance 04 + 22 + summary"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/04_*.sql
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/22_*.sql
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish=' || count(*) FROM core.dish WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'ingredient=' || count(*) FROM core.ingredient WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'fiber_calcium_dishes=' || count(*) FROM core.dish WHERE NOT is_deleted AND nutrition_snapshot ? 'dish_fiber_g' AND nutrition_snapshot ? 'dish_calcium_mg';"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'symptom_rows=' || count(*) || ' pending=' || count(*) FILTER (WHERE review_status='pending') || ' active=' || count(*) FILTER (WHERE is_active) FROM core.symptom_nutrient_map;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'knowledge_total=' || count(*) FROM knowledge.knowledge_doc WHERE NOT is_deleted;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'backlog=' || count(*) FROM knowledge.v_embedding_backlog;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'condition_rows=' || count(*) FROM core.health_condition;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'migrations=' || count(*) FROM audit.schema_migration;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'diet_app_super=' || rolsuper FROM pg_roles WHERE rolname='diet_app';"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'server=' || version();"
echo "[initdb 60] done"