FROM pgvector/pgvector:pg18

# 数据库交付资产（01 合并版 dump / 03 权限 / 04 验收 / 12 整改 / 14 RAG / 18 病种 / 19 主题 / 20 铁源纤维钙 / 21 反向营养 / 22 数据补充验收 / 41 反向营养审核激活 / 42 疾病规则口径审核 / 43 审核激活验收）
COPY database/ /delivery/

# 容器初始化脚本，空数据卷首次启动按文件名顺序自动执行
COPY docker/initdb/ /docker-entrypoint-initdb.d/
RUN chmod 0555 /docker-entrypoint-initdb.d/*.sh

LABEL org.opencontainers.image.title="diet-agent-pg 1.2r4" \
      org.opencontainers.image.description="PostgreSQL 18.7 + pgvector 0.8.7，空卷首启自动建 v1.2r4 合并版库并跑 04 + 22 + 43 验收（含反向营养 19 条激活、疾病规则 9 条审核启用）" \
      org.opencontainers.image.version="1.2r4"