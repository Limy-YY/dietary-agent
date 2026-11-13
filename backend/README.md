# 膳食搭配智能体系统 · 后端（FastAPI）

## 环境

- Python 3.13+（开发机 3.13.16）
- PostgreSQL 18（本地开发：Docker 容器 `diet-agent-pg`，库 `diet_agent`，端口 5432）
- 应用连接账号：`diet_app / diet_app_dev`（由 `scripts/grant_diet_app.sql` 创建授权；应用**不**使用超级用户）

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

## 已实现接口（2026-10-22）

| 接口 | 路由 | 说明 |
|---|---|---|
| 健康检查 | GET /api/health | 服务与数据库状态 |
| API-11（T1） | GET /api/ingredients/search?q=&limit= | 食材搜索：名称/别名匹配 + 营养明细 + 过敏原三态 + 完整性 |
| API-12（T2/T3） | GET /api/dishes/search?q=&exclude_allergies=&page=&page_size= | 菜式搜索：营养 + 完整性标记 + 过敏原过滤（decision/reason） |
| API-09（T11） | POST /api/calc/nutrition | 营养核算：菜式（×份量+油盐估算）/ 食材（生重×可食部）双口径，确定性计算 |
| API-20（T12） | GET /api/users/{user_id}/profile | 用户档案：基本信息 + 硬约束（过敏/忌口/疾病）+ 月经状态（extras） |
| API-13（T4/T5） | GET /api/nutrition/weekly-report?user_id=&week_start= | 周报：RNI/AI/UL 参考值对照 + 周度 UL 超限评估（sex 中英映射） |
| API-17/18/19（T6/T7/T8） | GET /api/condition-rules/catalog · /production · POST /evaluate | 疾病规则：目录（含审核状态）/ 正式规则 / 生产评估（未审核返回 rule_not_approved） |
| API-15/16（T9/T10） | POST /api/agent/rag-query · /reverse-nutrition | 知识检索（关键词兜底，向量 RRF 待 Agent 侧组件）+ 反向营养推理（表待补） |
| API-14（对话） | POST /api/agent/chat（SSE） | 多轮对话：会话自动创建 + 消息落库 + 归属校验；Agent 服务接入点占位待联调 |
| API-01 | POST /api/profile | 创建 / 更新用户档案（按 user_id upsert） |
| API-02 | GET /api/profile/{user_id} | 获取用户完整档案 |
| API-03 | POST /api/meal-plan/generate | 生成一日膳食方案（确定性骨架：过敏过滤 + 蛋白源优先贪心 + 油盐估算，落库） |
| API-04 | GET /api/meal-plan/{plan_id} | 获取单份历史膳食方案 |
| API-05 | GET /api/meal-plan/list?user_id=&page=&page_size= | 历史膳食方案列表（摘要分页） |
| API-06 | POST /api/meal-plan/weekly | 生成一周完整食谱（7 天落库，周度评估待 Agent 工作流） |

## 数据库恢复（一次性）

交付包 `数据库交付包/` 恢复方式见 `00_数据库交付说明.md`（本机已通过 Docker 完成：
`DATABASE DELIVERY ACCEPTED`）。
