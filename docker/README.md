# 数据库镜像 docker/

PostgreSQL 18.7 + pgvector 0.8.7。空数据卷首次启动即自动建成 v1.2r1 库（60 菜 / 128 食材 / 43 篇知识库），
并跑完 `04_数据库整体验收.sql`，日志里能看到 `[initdb 00]`～`[initdb 60]` 八个阶段。

## 来历与替换约定

`09_文件校验值.sha256` 一直登记着本目录 12 个文件的 sha256，但文件本体此前从未提交进仓库
（数据岗 `454a101` 只提交了 `database/19`、没带 `docker/`）。2026-11-16 后端按
`07_数据库交付说明.md` 与 `08_空库恢复与复跑说明.md` 的描述重建了等价实现，并实际 build + 首启验证通过，
文件命名与执行顺序与 08 的八步一一对应。

数据岗原版补传后，用原版覆盖本目录、同步更新 09 的 docker 段校验值即可；八步契约不变。

## 起库

```bash
cd docker && docker compose up -d --build
docker compose ps                       # 等 healthy，首次约 10 秒
docker exec -it diet-agent-db psql -U postgres -d diet_agent -c "select count(*) from core.dish;"
```

只 build 不起：

```bash
docker build -f docker/Dockerfile -t diet-agent-db:v1.2r1 .
```

build context 是仓库根（`database/` 要 COPY 进镜像的 `/delivery`）。

## 首次启动做的八步

| 脚本 | 内容 |
| --- | --- |
| `00_preflight.sh` | 校验 `/delivery` 七份资产齐全、建 `vector` 扩展 |
| `10_restore.sh` | `pg_restore` 还原 01 dump（60 菜基线） |
| `20_migrate.sh` | 应用 12，v1.2 → v1.2r1（写 r1 / r1b 迁移标记） |
| `30_grants.sh` | 应用 03，建 `diet_app` 应用账号并授权 |
| `40_conditions.sh` | 应用 18，补齐 4 个病种字典 |
| `50_vector.sh` | 应用 14，vector(1024) 列 + HNSW + 检索函数 |
| `55_topics.sh` | 应用 19，知识库 26 → 43 篇 |
| `60_verify.sh` | 跑 04 验收并输出关键计数 |

## 2026-11-16 首启实测

| 项 | 结果 |
| --- | --- |
| 八步执行 | 8/8 通过，整链 0 ERROR，约 9 秒完成 |
| `04` 摘要 11 项 | dishes 60 / goal_mappings 5 / ingredients 128 / key_micronutrients 7 / legacy_plans_preserved 3 / r1b 1 / r1 1 / schema_migration 1 / staging_schema_removed true / test_rows_after_rollback 3 / test_view_removed true |
| 知识库 | `knowledge_doc` 43，`v_embedding_backlog` 43 |
| 病种 | `health_condition` 4 |
| 迁移标记 | 4 条（product-v2 / dish-expansion-60 / review-r1 / review-r1b） |
| pgvector / 服务端 | 0.8.7 / PostgreSQL 18.7 |
| `diet_app` 是否超级用户 | **false**（`rolsuper=false`） |

## 三个注意点

1. **`POSTGRES_USER=postgres`**。官方镜像会把 `POSTGRES_USER` 建成超级用户；应用账号 `diet_app` 必须由 03 建，
   否则应用账号带超级用户权限。旧 `deploy/docker-compose.yml` 写的正是 `POSTGRES_USER: diet_app`，这也是它被作废的原因。
2. **数据卷挂 `/var/lib/postgresql`**。PG18 的 `PGDATA` 是 `/var/lib/postgresql/18/docker`，挂到 `/data` 子目录会让数据落在卷外，
   `down -v` 清不掉，重置失效。
3. **重置**：`docker compose down -v && docker compose up -d --build`，空卷重跑一次八步，约 10 秒回基线。
