FROM pgvector/pgvector:pg18

# 数据库交付资产（01 dump / 03 权限 / 04 验收 / 12 整改 / 14 RAG / 18 病种 / 19 主题）
COPY database/ /delivery/

# 八步初始化脚本，空数据卷首次启动按文件名顺序自动执行
COPY docker/initdb/ /docker-entrypoint-initdb.d/
RUN chmod 0555 /docker-entrypoint-initdb.d/*.sh

LABEL org.opencontainers.image.title="diet-agent-db v1.2r1" \
      org.opencontainers.image.description="PostgreSQL 18.7 + pgvector 0.8.7，空卷首启自动建 v1.2r1 库并跑 04 验收"