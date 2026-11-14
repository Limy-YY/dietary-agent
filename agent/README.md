# 膳食搭配智能体 · Agent 服务

独立 Agent 服务（FastAPI + DeepSeek），负责「一句话 → 建档/读档 → 生成方案 → 输出卡片」。**所有数值来自后端确定性计算（rule_engine / REST），大模型只做理解与组织语言，不自己算数。**

## 架构

```
前端 Vue ──SSE──> 后端 /agent/chat ──代理──> 本服务 /chat (8001)
                                              ├── 生成方案：进程内直调 rule_engine（读数据库）
                                              └── 其余能力：HTTP 调后端 REST（8000）
```

- 生成（五步算法、7 关键微量平衡）走 **rule_engine**（后端 `app/services/rule_engine`，进程内直调，不写库）；
- 档案 / 食材 / 菜式 / 核算 / 疾病规则 / RAG / 反向营养 / 周报 走 **后端 REST**；
- 输出对齐 `frontend/docs/agent-output-contract.md`（SSE 事件 + blocks）。

## 目录

| 文件 | 职责 |
|---|---|
| `main.py` | FastAPI 入口：`POST /chat`（SSE）、`GET /health` |
| `agent.py` | 意图路由 + 多轮内存态 + LLM 文本/分类 |
| `rule_engine_bridge.py` | import 后端 rule_engine；档案/请求映射；结果→plan |
| `blocks.py` | plan/REST 结果 → 前端 blocks |
| `backend_client.py` | 后端 REST 封装 |
| `config.py` | `.env` 配置读取 |

## 启动

```powershell
cd agent
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple/
copy .env.example .env   # 填 DEEPSEEK_API_KEY、DATABASE_URL 等
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

验证：浏览器打开 `http://127.0.0.1:8001/health`。

## 依赖后端

- **后端 REST 已在 8000 跑起**（`BACKEND_BASE_URL`）；
- **数据库 v1.2 已恢复**（rule_engine 读 `goal_structure_map` / `nutrient_reference` / 菜式配料 / `recent_micro_balance`）；
- **后端 `/agent/chat` 已接到本服务**：见 `../backend/app/routers/chat.py` 的代理（`AGENT_BASE_URL` 默认 `http://127.0.0.1:8001`）。

## 快速自测

先给 `demo-user` 建一份档案（后端 `/profile` 初始为空）：

```powershell
curl -X POST http://127.0.0.1:8001/chat -H "Content-Type: application/json" -d "{\"user_id\":\"demo-user\",\"message\":\"我是张三，28岁男生，178cm 82kg，久坐想减脂，对花生过敏，帮我配今天三餐\"}"
```

或直接连到已建好档案的用户：

```powershell
curl -X POST http://127.0.0.1:8001/chat -H "Content-Type: application/json" -d "{\"user_id\":\"demo-user\",\"message\":\"今天吃什么\"}"
```

返回应为 SSE 流：`message`(delta 正文) → `message`(meta.blocks 卡片) → `done`。

## 意图覆盖

| 输入 | 动作 |
|---|---|
| 今天吃什么 / 生成一日三餐 | 当日三餐（meal_card + nutrition + sources） |
| 生成一周食谱 | 七天方案 |
| 推荐一餐搭配 | 单餐 3 候选 |
| 换一换 / 更换午餐候选 | 切下一候选（内存态） |
| 确认当前方案 | 固定 + 食材清单 |
| 生成周膳食报告 | 周报（report） |
| 看完整食谱 / 看看食材清单 | 展开食谱 / 清单 |
| 减脂期怎么吃 / 高血压注意什么 | RAG 问答（sources） |
| 我口角炎、乏力… | 反向营养（medical_hint + sources） |
| 我是 XX，28 岁男生… | 建档 → 自动配餐 |

## 已知边界

1. **多轮状态在内存**：换候选/确认靠进程内 `_state`，重启即清空；生产应落库（`meal_plan` / `meal_slot` / `meal_candidate`）。
2. **用户身份**：前端暂不传 `user_id`，后端 `/agent/chat` 缺省 `demo-user`（JWT 骨架阶段）。正式接入时改从 token 解 user_id。
3. **rule_engine 不写库**：生成的方案只回给前端，未写 `app.meal_plan`；「当前规划/历史方案」面板的回读接口需要后端补落库。
4. **报告为粗版**：`report` 块目前只透传周报参考值，`daily_trend` / 达标率需后端 `/nutrition/analysis` 落地后细化。
5. **DeepSeek key**：未配置时结构化意图仍走正则+模板，RAG/症状/建档的个性化语言会退化，但不报错。
