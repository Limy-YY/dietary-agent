#!/bin/bash
set -euo pipefail
echo "[initdb 00] preflight: assets + vector extension"

# 显式资产清单：禁止 /delivery/N_*.sql 这类通配。
# 原因：psql -f a.sql b.sql 只执行第一个文件，其余静默丢弃（不报错、不提示），
# 见 BUG-055 / issue #20；而 database/ 下 37、41、44、52、61 号已有同号多文件。
# 用显式清单后，文件名被改/漏拷会在 00 步直接 MISSING 失败，而不是在 59 步静默跳过。
ASSETS=(
  "01_完整数据库备份_diet_agent_v1.2r2_合并版.dump"
  "03_应用账号与权限.sql"
  "04_数据库整体验收.sql"
  "12_数据库整改_v1.2_to_v1.2r1.sql"
  "14_RAG向量化_v1.2r1.sql"
  "18_病种字典补齐_v1.2r1.sql"
  "19_知识库主题扩充_v1.2r1.sql"
  "20_数据补充_铁源纤维钙_v1.2r2.sql"
  "21_反向营养映射_待审核_v1.2r2.sql"
  "22_数据补充验收_v1.2r2.sql"
  "37_meal_plan_is_executed_v1.2r3.sql"
  "39_过敏原状态核查修订_v1.2r4.sql"
  "41_RAG真实来源链接_v1.2r4.sql"
  "41_反向营养映射审核激活_v1.2r4.sql"
  "42_疾病规则口径审核_v1.2r4.sql"
  "43_审核激活验收_v1.2r4.sql"
  "44_博淇合并食材过敏原落定_v1.2r4.sql"
  "45_博淇v21基础菜合入_v1.2r4.sql"
  "46_博淇v21少盐变体_v1.2r4.sql"
)

missing=0
for f in "${ASSETS[@]}"; do
  if [ ! -f "/delivery/$f" ]; then
    echo "[initdb 00] MISSING /delivery/$f" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "[initdb 00] 资产缺失：database/ 与 docker/initdb/ 的显式清单不一致，请同步后再起库" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -t -A -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'vector=' || extversion FROM pg_extension WHERE extname='vector';"
echo "[initdb 00] ok"
