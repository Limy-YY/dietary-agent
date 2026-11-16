#!/bin/bash
set -euo pipefail
echo "[initdb 60] acceptance 04 + summary"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /delivery/04_*.sql
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'dish=' || count(*) FROM core.dish;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'ingredient=' || count(*) FROM core.ingredient;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'knowledge_total=' || count(*) FROM knowledge.knowledge_doc;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'backlog=' || count(*) FROM knowledge.v_embedding_backlog;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'condition_rows=' || count(*) FROM core.health_condition;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'migrations=' || count(*) FROM audit.schema_migration;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'diet_app_super=' || rolsuper FROM pg_roles WHERE rolname='diet_app';"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'server=' || version();"
echo "[initdb 60] done"