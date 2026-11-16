# 数据库镜像 docker/（v1.2r2）

PostgreSQL 18.7 + pgvector 0.8.7。空数据卷首次启动即自动建成 v1.2r2 合并版库
（60 菜 / 128 食材 / 43 篇知识库 / 16 条反向营养映射），并跑完 `04` 与 `22` 两套验收。

## 来历与替换约定

`09_文件校验值.sha256` 登记的是本目录 14 个文件（含 `56_nutrition_data.sh`、`57_reverse_nutrition.sh`），
但文件本体此前从未提交进仓库。2026-11-16 后端按 `07_数据库交付说明.md` 与 `08_空库恢复与复跑说明.md`
的描述重建了等价实现，并实际 build + 空卷首启验证通过；文件命名与执行顺序与 07/08 的十步一一对应。
数据岗原版补传后，用原版覆盖本目录、同步更新 09 的 docker 段校验值即可，十步契约不变。

## 构建与起库

```bash
# 只 build（context 取仓库根，database/ 要 COPY 进镜像的 /delivery）
docker build -f docker/Dockerfile -t diet-agent-pg:1.2r2 .

# 一键起库
cd docker && POSTGRES_PASSWORD=postgres_dev docker compose up -d
docker compose ps                        # 等 healthy，首次约 10 秒
docker compose logs -f db                # 看 [initdb NN] 十步
```

## 首次启动做的十步

| 脚本 | 内容 |
| --- | --- |
| `00_preflight.sh` | 校验 `/delivery` 十份资产齐全、建 `vector` 扩展 |
| `10_restore.sh` | `pg_restore --exit-on-error` 还原 `01` 合并版 dump |
| `20_migrate.sh` | 应用 12（v1.2 → v1.2r1 整改，写 r1 / r1b 标记） |
| `30_grants.sh` | 应用 03，建 `diet_app` 并授予最小权限 |
| `40_conditions.sh` | 应用 18，补齐 4 个病种字典 |
| `50_vector.sh` | 应用 14，vector(1024) + HNSW + 检索函数 |
| `55_topics.sh` | 应用 19，知识库 26 → 43 篇 |
| `56_nutrition_data.sh` | 应用 20，同步铁参考值、补纤维与钙、重算菜式汇总 |
| `57_reverse_nutrition.sh` | 应用 21，写入 16 条待审核反向营养映射 |
| `60_verify.sh` | 跑 04 + 22 验收，输出关键计数 |

`01` 是 v1.2r2 合并版 dump，本身已含 12/18/19/20/21 的结果；后面复跑这些脚本是**幂等验证**
（08 的实测口径就是「恢复后再依次复跑 12、03、18、14、19、20、21、04、22」），不是必须的前置步骤。

## 2026-11-16 首启实测（v1.2r2）

| 项 | 结果 |
| --- | --- |
| 十步执行 | 10/10 rc=0，整链 0 ERROR / 0 FATAL，约 10 秒完成 |
| `04` 摘要 11 项 | dishes 60、goal_mappings 5、ingredients 128、key_micronutrients 7、legacy_plans_preserved 3、r1 1、r1b 1、schema_migration 1、staging_schema_removed true、test_rows_after_rollback 3、test_view_removed true |
| `22` 摘要 12 项 | ingredients 128、dishes 60、dish_used_ingredients 57、dishes_with_fiber_calcium 60、iron_female_50_64 1 行 / 值 12、symptom_nutrient_rows 16、symptom_pending_rows 16、symptom_active_rows 0、symptom_key_nutrients 7、knowledge_docs 43、health_conditions 4 |
| 知识库 | `knowledge_doc` 43、`v_embedding_backlog` 43 |
| 迁移标记 | 4 条（product-v2 / dish-expansion-60 / review-r1 / review-r1b） |
| pgvector / 服务端 | 0.8.7 / PostgreSQL 18.7 |
| `diet_app` 是否超级用户 | **false**（`rolsuper=false`） |

## 四个注意点

1. **`POSTGRES_USER=postgres`**。官方镜像会把 `POSTGRES_USER` 建成超级用户；应用账号 `diet_app` 必须由 03 建，
   否则应用账号带超级用户权限（旧 `deploy/docker-compose.yml` 写的就是 `diet_app`，因此被作废）。
2. **数据卷挂 `/var/lib/postgresql`**。PG18 的 `PGDATA` 是 `/var/lib/postgresql/18/docker`，挂到 `/data` 子目录会让数据落在卷外，
   `down -v` 清不掉，重置失效。
3. **真实向量仍需灌库**。十步只建结构，`v_embedding_backlog` 仍是 43；灌库按 `16_RAG对齐与灌库说明.md` 跑 `15_RAG灌库脚本.py`。
4. **重置**：`docker compose down -v && docker compose up -d --build`，空卷重跑十步，约 10 秒回基线。
