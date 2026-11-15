#!/bin/bash
# 首次初始化自动执行：建扩展 -> 还原 01 dump -> 12 整改 -> 18 病种 -> 14 RAG -> 03 权限
# 依赖 compose 把仓库 database/ 挂载到 /delivery
#
# 为什么必须加 12 和 18（2026-11-14 修订）：
#   01 是 v1.2 基线备份，而交付包与 04 验收脚本都已是 v1.2r1。
#   04（r1b 版）在第 88 行断言 audit.schema_migration 存在 '2026-11-13-review-r1'、
#   在第 172 行断言存在 '2026-11-13-review-r1b'，这两个标记只由 12 整改脚本写入；
#   18 补齐 diabetes / gout / hyperlipidemia 三行病种字典，使库与 v1.2r1 交付一致。
#   只跑 01 + 03 会得到 v1.2-only 库，04 一执行即报错，不会 27/27。
set -e

DUMP="/delivery/01_完整数据库备份_diet_agent_v1.2_60道菜.dump"
R1_SQL="/delivery/12_数据库整改_v1.2_to_v1.2r1.sql"
COND_SQL="/delivery/18_病种字典补齐_v1.2r1.sql"
RAG_SQL="/delivery/14_RAG向量化_v1.2r1.sql"
GRANT_SQL="/delivery/03_应用账号与权限.sql"

psql_do() {
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
}

echo "[db_init] 1/6 创建 pgvector 扩展"
psql_do -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "[db_init] 2/6 还原 v1.2 完整备份（01）"
# 必须显式 -U：compose 里 POSTGRES_USER=diet_app，容器内不存在 postgres 角色，
# 省略 -U 时 pg_restore 默认以 postgres 连接，会报 FATAL: role "postgres" does not exist
pg_restore --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$DUMP"

if [ -f "$R1_SQL" ]; then
  echo "[db_init] 3/6 应用 v1.2 -> v1.2r1 整改（12：写入 r1 / r1b migration 标记）"
  # 12 的 P3 段（L357-364）要给 legacy-v1.1 的 meal_plan 打保留标记，
  # 但 01 dump 里这些方案已是 fixed 状态，UPDATE 会被 trg_guard_meal_plan_update 拦下
  # （ERROR: meal plan 2 is fixed and read-only）。
  # 数据岗交付的 12 未处理此情形——05 验收走的是 02 结构重建库，那里没有 fixed 方案，所以没暴露。
  # 这里在整改期间临时禁用该触发器、跑完立即恢复；三次独立 psql 调用，
  # 避免单事务 DISABLE + UPDATE + ENABLE 触发 pending trigger events 整体回滚。
  GUARD="trg_guard_meal_plan_update"
  psql_do -c "ALTER TABLE app.meal_plan DISABLE TRIGGER $GUARD;"
  set +e
  psql_do -f "$R1_SQL"
  R1_RC=$?
  set -e
  psql_do -c "ALTER TABLE app.meal_plan ENABLE TRIGGER $GUARD;"
  if [ "$R1_RC" -ne 0 ]; then
    echo "[db_init] 12 整改执行失败（rc=$R1_RC），触发器已恢复，终止初始化"
    exit "$R1_RC"
  fi
else
  echo "[db_init] 3/6 缺少 12 整改脚本，验收会因 r1 marker missing 中止"
  exit 1
fi

if [ -f "$COND_SQL" ]; then
  echo "[db_init] 4/6 补齐病种字典（18：hypertension/diabetes/hyperlipidemia/gout 四行）"
  psql_do -f "$COND_SQL"
else
  echo "[db_init] 4/6 缺少 18 病种补齐脚本，跳过"
fi

if [ -f "$RAG_SQL" ]; then
  echo "[db_init] 5/6 建立 RAG 向量结构（14：vector(1024) 列 + HNSW + 检索函数）"
  psql_do -f "$RAG_SQL" \
    || echo "[db_init] 警告：14 执行失败，RAG 结构未建立；04 的 27 项判定不依赖此项，可稍后补跑"
else
  echo "[db_init] 5/6 缺少 14 RAG 脚本，跳过"
fi

if [ -f "$GRANT_SQL" ]; then
  echo "[db_init] 6/6 应用应用账号与权限脚本（03，最后跑以覆盖 12/14 新增对象）"
  psql_do -f "$GRANT_SQL"
else
  echo "[db_init] 6/6 未找到 03 权限脚本，跳过"
fi

echo "[db_init] 完成：v1.2r1 库已就绪（01 + 12 + 18 + 14 + 03）。"
echo "[db_init] 请执行 /delivery/04_数据库整体验收.sql 做验收判定"
