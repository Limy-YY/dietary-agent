# 膳食搭配智能体系统 · 后端（FastAPI）

## 环境

- Python 3.13+（开发机 3.13.16）
- PostgreSQL 18（本地开发：Docker 容器 `diet-agent-pg`，库 `diet_agent`，端口 5432）
- 应用连接账号：`diet_app`（口令见 `.env`，不写入代码；由 `scripts/grant_diet_app.sql` 创建授权；应用**不**使用超级用户）

## 快速启动

```powershell
# 1. 创建虚拟环境并安装依赖（国内镜像）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple/

# 2. 启动
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. 验证
#   浏览器或 curl 访问 http://127.0.0.1:8000/api/health
#   OpenAPI 文档：http://127.0.0.1:8000/docs
```

## 项目结构

```
backend/
├── app/
│   ├── main.py          # 应用入口、路由注册、全局异常处理
│   ├── config.py        # .env 配置
│   ├── db.py            # SQLAlchemy 引擎与会话
│   ├── core/
│   │   ├── errors.py    # 业务错误码（契约 §2.5）
│   │   ├── response.py  # 统一响应结构（契约 §2.3）
│   │   └── security.py  # JWT 鉴权（契约 §2.2）
│   ├── routers/         # 路由（health 示例）
│   ├── schemas/         # Pydantic 请求/响应模型
│   ├── models/          # ORM 模型（业务表）
│   └── services/        # 业务逻辑（确定性计算、工具封装）
├── scripts/
│   └── grant_diet_app.sql
├── .env / .env.example
└── requirements.txt
```

## 约定（对应接口契约）

- 路由统一 `/api` 前缀，省略 `/api/` 在契约中的写法（契约 §2.1）
- 响应统一 `{code, message, data}`，`code=0` 成功（契约 §2.3）
- 错误码与状态码映射见契约 §2.4 / §2.5
- 鉴权：`Authorization: Bearer <token>`（契约 §2.2，当前为骨架，签发见 `core.security.create_access_token`）

## 已实现接口（v1.2，2026-11-14）

| 接口 | 路由 | 说明 |
|---|---|---|
| 健康检查 | GET /api/health | 服务与数据库状态 |
| API-01/02 | PUT /api/profile · GET /api/profile | 档案 v1.2 十一项可写；`target_calories` 由后端按 BMR×1.4 计算落库；`POST /api/profile` 为兼容别名 |
| API-04 | GET /api/meal-plan/{plan_id} | 方案详情（slots → candidates → dishes 四级出参） |
| API-05 | GET /api/meal-plan/list?page=&page_size= | 方案列表摘要分页 |
| API-21 | GET /api/meal-plan/current | 当前规划面板 |
| API-22 | POST /api/meal-plan/week/generate | 用户自定范围生成，落库 `status=candidates` |
| API-23 | POST /api/meal-plan/candidate/swap | 换候选，写 `app.plan_adjustment` 留痕并返回 `macro_delta` |
| API-24 | POST /api/meal-plan/week/fix | 固定方案，触发器补 `fixed_at` 并同步 `shopping_list` |
| API-25 | POST /api/nutrition/analysis | 7 关键微量跨日平衡，日均口径（`summary.basis=daily_average`），缺值返 null 不判达标 |
| API-26 | GET /api/nutrition/report | 膳食报告面板只读 |
| API-27 | GET /api/shopping-list | 食材清单，按 `core.ingredient.category` 分组 |
| API-09 | POST /api/calc/nutrition | 营养核算：菜式（份量+油盐估算）/ 食材（生重×可食部）双口径 |
| API-11 | GET /api/ingredients/search?q=&limit= | 食材搜索，含 `purine_level / sfa_g / iodine_ug / data_quality / source_note` |
| API-12 | GET /api/dishes/search?q=&exclude_allergies= | 菜式搜索，过敏原三态判定（decision / reason） |
| API-14 | POST /api/agent/chat（SSE） | 六事件 session / message / artifact / clarify / error / done；Agent 服务接入点待联调 |
| API-15 | POST /api/agent/rag-query | 知识检索：当前关键词兜底，向量 + RRF 待 pgvector 与 embedding 就绪 |
| API-16 | POST /api/agent/reverse-nutrition | 反向营养，附就医提示（`symptom_nutrient_map` 待数据岗补表） |
| API-17/18/19 | GET /api/condition-rules/catalog · /production · POST /evaluate | 疾病规则目录（含审核状态）/ 正式规则 / 生产评估 |
| 病种字典 | GET /api/conditions · /api/conditions/catalog | 档案三态选择 `condition_id` 的取值域，读 `core.health_condition`（与 `/condition-rules/catalog` 的规则目录不同） |
| API-20 | GET /api/users/{user_id}/profile | 用户档案，复用档案同一 SQL 与序列化 |

> 鉴权：除 `/api/health` 外统一 `Authorization: Bearer <JWT>`，`user_id` 由 token 注入，不再走查询参数。
> 能量口径：v1.2 删 `activity_level`，统一 `BMR(Mifflin-St Jeor) × 1.4`，**不做热量缺口/盈余**，健康目标只改结构比例。依据 2026-11-14 项目组裁决（按契约 §0.2）；SRS FR-09/10 的四档活动系数与减脂 −500 为旧口径，不再适用，缺口/盈余留待后期改进。
> 实现落点：`rule_engine/targets.py` 的 `bmr × goal_structure_map.activity_factor`（库内五条目标均为 1.4）、`profile.py` 的 `target_calories`、`mealplan` 直接取引擎 `targets.energy_kcal`——三处同源同值，接口层不再自算热量。
> 营养口径：多日方案一律折日均后与每日参考量比较；任一餐位缺值的指标返 null，不判「不足/达标」。

## RAG（API-15）待接入说明

向量侧参数已按 Agent 岗 `11.14/embedding-contract.md`（2026-11-14 定稿）**定死，不再改**：

| 项 | 值 |
|---|---|
| 模型 / 维度 | `BAAI/bge-m3` / **1024**（改维度须重建 HNSW 索引） |
| 端点 | 默认 SiliconFlow `https://api.siliconflow.cn/v1`（OpenAI 兼容，需 `EMBEDDING_API_KEY`）；备选 Ollama 本地 `http://127.0.0.1:11434` |
| 检索函数 | `knowledge.search_documents(p_query, p_query_embedding, p_limit=5, p_min_similarity=0.5, p_rrf_k=60)` |
| RRF | `k=60`；关键词 : 向量 = 1 : 1；每路池 20；融合后取 `top_k=5` |

**当前阻塞**：容器镜像为 `postgres:18`，`pg_available_extensions` 无 `vector`，`14_RAG向量化_v1.2r1.sql` 首段即抛异常，导致 `knowledge_doc.embedding` 列、HNSW 索引与检索函数均不存在。故 `POST /agent/rag-query` 暂时保留关键词兜底。
**解除后改动**：仅需在 `routers/agent.py` 把查询词送 embedding 端点取 1024 维向量，再调用上述函数；请求与出参结构不变，前端无需改动。

## 数据库恢复（一次性）

交付包 `数据库交付包/` 恢复方式见 `00_数据库交付说明.md`（本机已通过 Docker 完成：
`DATABASE DELIVERY ACCEPTED`）。
