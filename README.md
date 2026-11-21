# 膳食搭配智能体系统「膳宝」

> 团队「海底小纵队」· 福州大学 2026 秋软件工程课程项目

## 项目简介

本项目旨在开发一个膳食搭配智能体，以对话为唯一入口，提供食谱搭配、膳食报告、营养咨询等个性化功能，帮助用户依据自身身体参数与健康目标，获得结构清晰、有依据、可长期坚持的膳食方案。

---

## 技术栈

| 层     | 技术                                                       |
| ------ | ---------------------------------------------------------- |
| 前端   | Vue 3 + Vite + Element Plus + Pinia + Vue Router + Axios   |
| 后端   | FastAPI（Python 3.13）                                     |
| Agent  | FastAPI + DeepSeek（OpenAI 兼容 SDK），意图路由 + 工具编排 |
| 数据库 | PostgreSQL 18 + pgvector 0.8                               |
| 测试   | pytest 契约断言 + Playwright UI 冒烟                       |

## 系统架构

五层业务架构 + 两个横切层（自上而下逐层调用）：

```
接口层（FastAPI：REST + SSE 流式对话）
  → Agent 层（单一对话 Agent：意图路由 + 工具编排）
  → 规则引擎层（确定性工具：生成/换候选/重算/回溯，纯代码）
  → 知识库层（RAG：pgvector 向量 + 关键词 RRF 混合检索）
  → 数据层（PostgreSQL + pgvector，schema 分 core/knowledge/app/audit）
横切：初始化层（建表 + 种子数据 + 向量化）、评测层（意图路由/结构化输出/候选达标率/性能）
```

> **核心原则**：输出什么、展示什么由 Agent 通过其**输出契约（结构化 JSON Schema）**决定，前端只负责渲染，不预设业务逻辑；计算与决策分离——规则引擎负责「算对」，Agent 负责「理解、决策、沟通」。详见 [frontend/docs/agent-output-contract.md](frontend/docs/agent-output-contract.md)。

## 目录结构

| 目录                  | 说明                                                                     |
| --------------------- | ------------------------------------------------------------------------ |
| [frontend/](frontend/) | 前端界面（Vue 3 + Vite）：对话流 + schema 渲染器 + 右侧四面板 + 轻量档案 |
| [backend/](backend/)   | 后端服务（FastAPI，:8000）：REST + SSE、规则引擎、RAG、数据访问层        |
| [agent/](agent/)       | 对话 Agent 服务（:8001）：意图路由 + 工具编排 + 输出契约                 |
| [database/](database/) | 数据库交付包 v1.2r4（128 食材 / 120 菜 / 43 知识库 / 19 条已启用反向营养映射 / 9 条已审核疾病规则） |
| [docker/](docker/)     | PostgreSQL 18 + pgvector 镜像，一键起库，空卷自动建库                    |
| [tests/](tests/)       | 契约断言自动化测试                                                       |
| [deploy/](deploy/)     | 部署运维配置（历史；一键起库已迁至 docker/）                             |
| [docs/](docs/)         | 各次作业材料 + 测试资产                                                  |

根目录脚本：

- [start-local.bat](start-local.bat) / [start-local.ps1](start-local.ps1)：一键起库 → 后端 8000 → Agent 8001
- [restart-local.bat](restart-local.bat) / [restart-local.ps1](restart-local.ps1)：重启后端 + Agent（不动库）

## 运行方式

### 环境要求

- Docker Desktop（用于启动数据库容器 `diet-agent-db`）
- Python 3.13（后端与 Agent 共用根目录 `.venv`）
- Node.js（前端构建与开发）

### 启动步骤

```bash
# 一键：起库（含建 diet_backend 账号）→ 后端 8000 → Agent 8001
github仓库/start-local.bat

# 前端另起（:5173）
cd github仓库/frontend && npm run dev
```

各服务与验证地址：

| 服务                                    | 端口 | 验证                                                           |
| --------------------------------------- | ---- | -------------------------------------------------------------- |
| 数据库（Docker 容器 `diet-agent-db`） | 5432 | `docker compose ps`（healthy）                               |
| 后端                                    | 8000 | `http://127.0.0.1:8000/api/health`（status=ok, database=ok） |
| Agent                                   | 8001 | `http://127.0.0.1:8001/health`（llm=true）                   |
| 前端                                    | 5173 | `http://127.0.0.1:5173`                                      |

> 前端默认已接真实后端（[frontend/.env.development](frontend/.env.development) `VITE_USE_MOCK=false` + `VITE_API_BASE=http://127.0.0.1:8000`）；不装后端时可改回 `true` 走内置 Mock。

### 鉴权

接口无登录端点，JWT 由 `backend/.env` 的 `JWT_SECRET` 离线签发。离线签发 token：

```cmd
cd backend
..\.venv\Scripts\python.exe -c "from app.core.security import create_access_token; print(create_access_token('demo-user', 1440))"
```

> 注意：venv 在**仓库根目录** `github仓库\.venv`（后端与 Agent 共用），不在 `backend` 下，所以从 `backend` 目录执行时要写成 `..\.venv\Scripts\python.exe`（Windows 用反斜杠）。

浏览器控制台注入后刷新即可：

```js
localStorage.setItem('sz_token', '<token>')
```

除 `/api/health` 外，所有业务接口带 `Authorization: Bearer <token>`，`user_id` 由 token 注入。

## 作业材料（docs/）

| 目录                                    | 作业                                       | 内容                                               |
| --------------------------------------- | ------------------------------------------ | -------------------------------------------------- |
| [docs/assignment_1/](docs/assignment_1/) | 第一次作业：团队展示 + 选题报告 + 需求分析 | 需求分析文档、用户调研、智能体定制对比、答辩 PPT   |
| [docs/assignment_2/](docs/assignment_2/) | 第二次作业：原型设计 + 概要设计            | 系统/数据库设计说明书、数据库交付包 v1.1、原型链接 |

测试资产在 [docs/testing/](docs/testing/)：测试计划、测试报告、116 条用例 + 缺陷清单（xlsx）、离线自动化断言。

## 数据库交付包（database/）

数据库交付包 v1.2r4：128 食材 / 120 菜 / 43 篇知识库 / 19 条已启用反向营养映射 / 9 条已审核疾病规则（7 条生效）/ 4 病种字典。

- 交付说明：[database/07_数据库交付说明.md](database/07_数据库交付说明.md)
- 空库恢复与复跑：[database/08_空库恢复与复跑说明.md](database/08_空库恢复与复跑说明.md)
- 本轮审核记录与口径：[database/44_本轮审核记录与口径说明_v1.2r4.md](database/44_本轮审核记录与口径说明_v1.2r4.md)
- 一键起库（[docker/](docker/)）：空数据卷首次启动自动建成 v1.2r4 合并版库并跑完三套验收（04 + 22 + 43），约 10 秒。
