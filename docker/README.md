# 数据库镜像 docker/（v1.2r4）

PostgreSQL 18.7 + pgvector 0.8.7。空数据卷首次启动即自动建成 v1.2r4 合并版库
（120 菜 / 128 食材 / 43 篇知识库 / 19 条已启用反向营养映射 / 9 条已审核疾病规则），并跑完 `04`、`22`、`43` 三套验收。

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

## 首次启动做的十四步

| 脚本 | 内容 |
| --- | --- |
| `00_preflight.sh` | 按显式清单校验 `/delivery` 19 份资产（01/03/04/12/14/18/19/20/21/22/37/39/41×2/42/43/44/45/46，缺一即失败）、建 `vector` 扩展 |
| `10_restore.sh` | `pg_restore --exit-on-error` 还原 `01` 合并版 dump |
| `20_migrate.sh` | 应用 12（v1.2 → v1.2r1 整改，写 r1 / r1b 标记） |
| `30_grants.sh` | 应用 03，建 `diet_app` 并授予最小权限 |
| `40_conditions.sh` | 应用 18，补齐 4 个病种字典 |
| `50_vector.sh` | 应用 14，vector(1024) + HNSW + 检索函数 |
| `55_topics.sh` | 应用 19，知识库 26 → 43 篇 |
| `56_nutrition_data.sh` | 应用 20，同步铁参考值、补纤维与钙、重算菜式汇总 |
| `57_reverse_nutrition.sh` | 应用 21，写入审核修订后的 13 条待审核反向营养映射 |
| `58_executed.sh` | 应用 37，补 `meal_plan.is_executed` 打卡字段 |
| `59_rag_sources.sh` | 应用 41_RAG真实来源链接（已核查 RAG 来源 URL） |
| `59_review_activation.sh` | 应用 41（反向营养审核激活 → 19 条）、42（疾病规则口径审核 → 9 条）、43（激活后验收） |
| `59v_v21_merge.sh` | 应用 39 + 45 + 44 + 46，补齐 v21 基线至 213 道（170 普通 + 43 少盐） |
| `60_verify.sh` | 跑 04 + 22 + 43 验收，输出关键计数 |

`01` 是 v1.2r2 合并版 dump，本身已含 12/18/19/20/21 的结果；后面复跑这些脚本是**幂等验证**
（08 的实测口径就是「恢复后再依次复跑 12、03、18、14、19、20、21、04、22」），不是必须的前置步骤。

## 文件名与通配（BUG-055 / issue #20）

`database/` 里已经有同号多文件：`37`（.md 说明 + .sql）、`41`（RAG 来源链接 + 反向营养激活）、
`44`（.md 说明 + .sql）、`52`、`61`。因此**initdb 脚本一律写显式文件名，禁止 `psql -f /delivery/41_*.sql` 这类通配**：

- `psql -f a.sql b.sql` 只会执行第一个文件，其余**静默丢弃**（不报错、不提示），现象是「步骤打印 ok，但数据没变」；
- 41 撞车的后果就是反向营养停在 16 条 pending → `43` 断言「应为 19 条」必挂 → initdb 中断；
- 现在 `00_preflight.sh` 用显式清单前置校验，文件名被改/漏拷会在 00 步 `MISSING` 直接失败，
  而不是到 59/60 步才暴露；新增脚本时必须同时更新 `00_preflight.sh` 的 `ASSETS`。

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

## 2026-11-19 本轮增量（v1.2r4）

`59_review_activation.sh` 这步是这轮新增的，做两件事，并各自带自检：

| 脚本 | 内容 | 期望计数 |
| --- | --- | --- |
| `41_反向营养映射审核激活_v1.2r4.sql` | 清掉 3 类旧稿残留 → 按 37 号审核文本激活 13 条 → 补 6 条高频症状（掉发/便秘/失眠/腿抽筋/口腔溃疡/皮肤干燥） | 19 条 approved+active，moderate 8 / low 11，关键微量 7/7 |
| `42_疾病规则口径审核_v1.2r4.sql` | 高血压钠目标互斥收敛（2000mg 唯一生效）+ DASH 模式转建议型 + 糖尿病/痛风/高血脂 5 条模式偏好与复核闸门 + 审批留痕 | 9 条 approved、7 条生效、`v_production_condition_rules` 7 条、4 病种覆盖 |
| `43_审核激活验收_v1.2r4.sql` | 只读验收：计数、分级、来源/审核字段、`乏力 掉发` 双命中、模式规则不被数值评估 | 全部断言通过 |

`22` 号验收已改为按阶段判定（`audit.schema_migration` 里有无 41 号迁移记录）：激活前 13/13/0（7/6），
激活后 19/0/19（8/11）。因此 `22` 单独跑在旧库上仍通过，跑在 `59` 之后也通过。

## 四个注意点

1. **`POSTGRES_USER=postgres`**。官方镜像会把 `POSTGRES_USER` 建成超级用户；应用账号 `diet_app` 必须由 03 建，
   否则应用账号带超级用户权限（旧 `deploy/docker-compose.yml` 写的就是 `diet_app`，因此被作废）。
2. **数据卷挂 `/var/lib/postgresql`**。PG18 的 `PGDATA` 是 `/var/lib/postgresql/18/docker`，挂到 `/data` 子目录会让数据落在卷外，
   `down -v` 清不掉，重置失效。
3. **真实向量仍需灌库**。十步只建结构，`v_embedding_backlog` 仍是 43；灌库按 `16_RAG对齐与灌库说明.md` 跑 `15_RAG灌库脚本.py`。
4. **重置**：`docker compose down -v && docker compose up -d --build`，空卷重跑十步，约 10 秒回基线。
