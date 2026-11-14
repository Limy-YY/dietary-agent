#!/bin/bash
# 首次初始化自动执行：建扩展 -> 还原 01 dump -> 应用 03 权限脚本
# 依赖 compose 把仓库 database/ 挂载到 /delivery
set -e

DUMP="/delivery/01_完整数据库备份_diet_agent_v1.2_60道菜.dump"
GRANT_SQL="/delivery/03_应用账号与权限.sql"

echo "[db_init] 1/3 创建 pgvector 扩展（若镜像支持）"
psql -v ON_ERROR_STOP=0 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;" \
  || echo "[db_init] 警告：vector 扩展创建失败（镜像不含 pgvector？），向量接线里程碑前不阻塞验收"

echo "[db_init] 2/3 还原 v1.2 完整备份"
pg_restore --no-owner --no-privileges -d "$POSTGRES_DB" "$DUMP"

if [ -f "$GRANT_SQL" ]; then
  echo "[db_init] 3/3 应用应用账号与权限脚本"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$GRANT_SQL" \
    || echo "[db_init] 提示：03 权限脚本执行失败不影响数据验收，可由 DBA 手工执行"
else
  echo "[db_init] 3/3 未找到 03 权限脚本，跳过"
fi

echo "[db_init] 完成。请执行 /delivery/04_数据库整体验收.sql 做验收判定"
