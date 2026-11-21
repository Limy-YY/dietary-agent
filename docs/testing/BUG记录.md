# 膳宝 · Bug 记录（α 冲刺联调）

> 记录联调 / debug 过程中发现的缺陷，逐条追加。
> 状态取值：`未修` / `已修·待部署` / `已闭环` / `已闭环`。
> 记录日期：2026-11-16 起。
>
> **2026-11-17 实机验证**：本地全栈（后端 8000 / Agent 8001 / 前端 5173，DeepSeek 接通）端到端跑通「建档→生成→换候选→确认→清单→当前规划→报告」，并补测周方案跨日差异化 / 解释 / 周报告 / RAG / 重复固定冲突。BUG-001~028 均已闭环（BUG-027 于 11-19 修复并 LIVE 验收关闭，详见下方该条）。
>
> **2026-11-17 营养咨询复核**：补测「反向营养/症状咨询 + RAG 知识问答」链路，新增 BUG-026（症状咨询检索为空仍追加「由文献库提供参考」假出处）、BUG-027（RRF 混合检索丢 source/source_id）。

---

## 总览

| # | 标题 | 层面 | 状态 |
|---|---|---|---|
| BUG-001 | 浏览器跨域被 CORS 拦截 | 前端 | 已闭环 |
| BUG-002 | `/api/agent/chat` 请求体缺 `user_id` 报 400 | 后端 schema | 前端兜底已修；正解待后端 |
| BUG-003 | `conversation_id` 字符串导致 int 校验失败 | Mock/真后端契约 | 前端兜底已修；正解待 Mock 对齐 |
| BUG-004 | `meal_card` 的 `total_kcal` / 候选 `kcal` 恒为 0 | 后端/Agent 契约 | 已闭环 |
| BUG-005 | 餐卡菜名全部显示「未命名菜品」 | 后端序列化 | 已闭环 |
| BUG-006 | 候选解释 `why_text` 被丢弃 | Agent blocks.py | 已闭环 |
| BUG-007 | 生成方案后未写入 `current_plan` 内存态，换候选/确认报「还没有待确认的方案」 | Agent 内存态 | 已闭环 |
| BUG-008 | 真 Agent 的 markdown 回复未渲染，`**`/`##`/列表符原样露出 | 前端渲染 | 已闭环 |
| BUG-009 | 膳食报告面板弹「接口不存在」（后端 HTTP 404 + code 1004 被误报） | 前端错误处理 | 已闭环 |
| BUG-010 | Agent 连库默认账号 `diet_app` 是 NOLOGIN，照抄 `.env.example` 连不上库 | Agent 配置 | 已闭环 |
| BUG-011 | 「当前规划」面板永远空态（`normalizeCurrentPlan` 认不出真后端结构） | 前端 schema | 已闭环 |
| BUG-012 | 系统代理导致 localhost 互调 502（httpx/requests 默认走代理） | 后端/Agent 出站请求 | 已闭环 |
| BUG-013 | 「为什么这样搭」解释请求超时（DeepSeek 慢 + 后端 60s 超时） | 超时配置/模型性能 | 已闭环 |
| BUG-014 | 点早餐餐位「换一换」→ Agent 报「没找到对应的餐位」 | Agent 槽位查找 | 已闭环 |
| BUG-015 | 「选用候选」匹配不上（后端候选无 `name` 字段） | Agent 候选匹配 | 已闭环 |
| BUG-016 | 确认方案后聊天里的食材清单卡片为空（`_shopping_list` 读错结构） | Agent 清单来源 | 已闭环 |
| BUG-017 | 「生成报告」走离线预览 / 报告卡片被丢弃 | Agent 报告链路 | 已闭环 |
| BUG-018 | 同一时间段多次确认/固定不同方案 → 膳食报告重复累计 | 后端/Agent/DB | 已闭环 |
| BUG-019 | 对话 markdown 正文块间空行（pre-wrap 泄漏到 AI 气泡） | 前端渲染 | 已闭环 |
| BUG-020 | 周餐卡 21 个餐位平铺、不按天分组折叠（Agent 丢 `slot_date`） | Agent blocks.py / 前端渲染 | 已闭环 |
| BUG-021 | 「当前规划」点「查看膳食报告」只切到报告面板、无动作 | 前端交互 | 已闭环 |
| BUG-022 | 微量「超标」误判：超过推荐量 100% 即判超标（应对 UL 判） | 后端营养判定 / 前端展示 | 已闭环 |
| BUG-023 | 一餐搭配「选项切换」不灵敏：点候选要等几秒或点多次才切 | 前端交互 / Agent 叙事链路 | 已闭环 |
| BUG-024 | Agent 生成方案后引导「去当前规划面板看餐卡」，但当前规划存的是已固定方案 | Agent 叙事引导文案 | 已闭环 |
| BUG-025 | 点「换一换」右侧工具栏整体刷新（换候选只改草稿却触发四面板重载） | 前端面板刷新触发 | 已闭环 |
| BUG-026 | 症状咨询检索为空仍追加「由文献库提供参考」假出处（违反可溯源铁律） | Agent 叙事 | 已闭环 |
| BUG-027 | RRF 混合检索丢 source/source_id（接口返回 null，可溯源落空） | 后端检索 / DB 函数 | 已闭环（4f6c937，issue #12） |
| BUG-028 | 过敏原「海鲜」「麸质」勾选后不拦截对应菜品（词表映射缺口） | 规则引擎硬过滤（后端） | 已闭环 |
| BUG-029 | 停止生成后消息上方残留「正在生成配餐方案」状态 | 前端 | 已修 |
| BUG-030 | 确认方案遇同期固定方案冲突只弹裸警告、无「替换/取消」 | Agent/前端 | 已修 |
| BUG-031 | 早/晚能量占比 25/35 与规范 30/30 不符 | 规则引擎 | 未修 |
| BUG-032 | 缺钠(null)被当硬排除，候选被静默丢弃（违反 null≠0） | 规则引擎 | 已修（2026-11-21） |
| BUG-033 | 跨日微量平衡查错时间窗口（查自身未来日期） | 规则引擎 | 未修 |
| BUG-034 | 清真/伊斯兰忌口漏排除猪肉「里脊/肉片/肉末」菜 | 规则引擎 | 未修 |
| BUG-035 | 已确诊疾病(confirmed_conditions)未参与候选硬过滤 | 规则引擎 | 未修 |
| BUG-036 | 对话建档几乎必然 422 静默失败，宗教忌口/厨具从不落库 | Agent | 未修 |
| BUG-037 | local_edit_only 误拦截「整份重新生成」请求 | Agent | 未修 |
| BUG-038 | 报告自定义日期区间字段名不匹配(start/end vs period) | Agent | 未修 |
| BUG-039 | 单菜替换硬编码 allow_approximate=True，未经同意落库近似结果 | Agent | 未修 |
| BUG-040 | swap_candidate 多日方案无法定位餐位（缺日期参数） | Agent | 未修 |
| BUG-041 | Agent 直连 /chat 异常只发 error 不发 done | Agent | 已修（2026-11-21） |
| BUG-042 | _parse_date_range 跨年日期区间解析错误 | Agent | 未修 |
| BUG-043 | 发送与会话历史懒加载竞态，流式消息整组丢失 | 前端 | 已修（2026-11-21） |
| BUG-044 | done 事件无条件覆写 error 状态 | 前端 | 已修（2026-11-21） |
| BUG-045 | 结构化块 __key 从未赋值，就地替换组件实例复用串脏 | 前端 | 未修 |
| BUG-046 | 「当前规划」面板确认方案未处理 2005 冲突 | 前端 | 未修 |
| BUG-047 | 食材清单勾选状态跨方案串数据 | 前端 | 未修 |
| BUG-048 | 档案编辑态可能回显默认值(load 未 await) | 前端 | 未修 |
| BUG-049 | 应用库账号缺 DELETE 权限，整餐重生成/替换单菜/删会话运行时失败（换一换按钮不受影响） | 数据库权限/后端 | 已修·待部署 |

---

## BUG-001 · 浏览器跨域被 CORS 拦截

- **现象**：浏览器控制台报 `Access to XMLHttpRequest ... blocked by CORS policy: No 'Access-Control-Allow-Origin' header`，所有接口 `net::ERR_FAILED`。
- **层面**：前端请求层。
- **根因**：[frontend/src/api/http.js](github仓库/frontend/src/api/http.js) 的 `apiBase()` 在非 Mock 模式返回**绝对后端地址**（`https://隧道/api`），axios/fetch 直接跨域打后端，绕过了 [vite.config.js](github仓库/frontend/vite.config.js) 里配好的 `/api` 代理。
- **为什么以前没暴露**：真后端验证全用 `curl`（不触发 CORS），浏览器测试全用 Mock 模式。**「浏览器 + 真后端」这条路径是第一次跑。**
- **状态**：已闭环。
- **修复**：`apiBase()` 开发态统一返回相对 `/api`，交给 Vite 代理转发（生产构建行为不变）。

## BUG-002 · `/api/agent/chat` 请求体缺 `user_id` 报 400

- **现象**：`参数校验失败: [{'type':'missing','loc':('body','user_id'),'msg':'Field required'}]`。
- **层面**：后端 schema。
- **根因**：[backend/app/schemas/chat.py](github仓库/backend/app/schemas/chat.py) 的 `ChatRequest.user_id` 是**必填**，但身份本应从 token 取（[chat.py](github仓库/backend/app/routers/chat.py) 里已有 `req.user_id = decode_token(token)` 覆盖逻辑）；前端契约从没发过 `user_id`。
- **状态**：前端兜底已修（发空串过校验）；**正解待后端**改 `user_id: str | None = None`。
- **修复**：前端 [agent.js](github仓库/frontend/src/api/agent.js) 补 `user_id: ''`；正解见 `backend/app/schemas/chat.py`。

## BUG-003 · `conversation_id` 字符串导致 int 校验失败

- **现象**：`int_parsing ... unable to parse string as an integer, input: 'conv_1794669469471'`。
- **层面**：Mock 与真后端契约不一致。
- **根因**：Mock 用 `conv_<时间戳>` 字符串 id，真后端 `conversation_id` 是 int；从 Mock 切到真后端后，localStorage 里残留的 Mock 会话把字符串 id 发给了真后端。
- **状态**：前端兜底已修（只发整数 id）；**正解待 Mock 对齐**（Mock 的 `conversation_id` 应改为整数，与真后端一致）。
- **修复**：前端 [agent.js](github仓库/frontend/src/api/agent.js) 过滤非整数 `conversation_id`。

## BUG-004 · `meal_card` 的 `total_kcal` / 候选 `kcal` 恒为 0

- **现象**：餐卡 artifact 里 `total_kcal: 0`、`slot.kcal: 0`、`candidate.kcal: 0`、副标题「全天约 0 kcal」；真值只存在于 `macro_estimate.kcal`。
- **层面**：后端 / Agent 输出契约。
- **根因**：后端只填 `macro_estimate.kcal`，[agent/blocks.py](github仓库/agent/blocks.py) 的 `_slot_view` 却读 `c.get("kcal")`（→0）、汇总字段也没填。
- **状态**：已闭环（[agent/blocks.py](github仓库/agent/blocks.py) 改为从契约字段 `macro_estimate.kcal` 取候选热量，并透传 `meal_plan_id` / `plan_type` / `goal_energy_kcal` 等契约字段）。

## BUG-005 · 餐卡菜名全部显示「未命名菜品」

- **现象**：餐卡每道菜名都显示「未命名菜品」。
- **层面**：后端序列化。
- **根因**：[backend/app/routers/mealplan.py](github仓库/backend/app/routers/mealplan.py) 的 `_serialize_candidate` 每道菜只吐 `dish_id`，没吐 `name`（菜名在 `core.dish` 表，`meal_candidate_dish` 关联表没存，序列化时也没去查）。
- **状态**：已闭环。
- **修复**：`mealplan.py` 新增 `_dish_names()` 批量查 `core.dish.name`，`_serialize_candidate/_serialize_slot/_serialize_plan` 注入 `name` 字段；同时补 `chat.py` 的 `_serialize_plan(plan, db)`（原调用漏传 `db`，会导致 `current_plan` 刷新时 `TypeError`）。

## BUG-006 · 候选解释 `why_text` 被丢弃

- **现象**：候选的「为什么这样搭」说明为空。
- **层面**：Agent blocks.py 字段映射。
- **根因**：[agent/blocks.py](github仓库/agent/blocks.py) 的 `_slot_view` 读 `c.get("desc")`，而后端 `_serialize_candidate` 给的是 `why_text`，字段名对不上。
- **状态**：已闭环（`_slot_view` 候选新增 `why_text` / `reason_codes` / `oil_salt_estimate` / `eating_order_advice` / `rank` 透传）。

## BUG-007 · 生成方案后未写入 current_plan 内存态

- **现象**：生成方案后点「换候选」或「确认」，Agent 报「还没有待确认的方案」。
- **层面**：Agent 内存态。
- **根因**：[agent/agent.py](github仓库/agent/agent.py) 生成分支里 `bc.generate_meal_plan()` 拿到 plan 后没写回 `_user_state(user_id)["current_plan"]`（重构漏写），而「换候选 / 确认」从 `_user_state` 读当前方案。
- **状态**：已闭环（补 `_user_state(user_id)["current_plan"] = plan`）。

## BUG-008 · 真 Agent 的 markdown 回复未渲染

- **现象**：真模型回复（如「为什么这样搭」的解释）里 `**加粗**`、`## 标题`、`- 列表`、数字列表原样显示，markdown 语法没渲染成格式。
- **层面**：前端渲染。
- **根因**：[frontend/src/components/chat/ChatMessage.vue](github仓库/frontend/src/components/chat/ChatMessage.vue) 用 `{{ message.text }}` 纯文本插值渲染助手正文，没做 markdown 解析。Mock 回复是纯文本，故「浏览器 + Mock」阶段没暴露。
- **状态**：已闭环。
- **修复**：引入 markdown-it（`html:false` 转义防 XSS、`linkify` + `breaks`），新增 [frontend/src/utils/markdown.js](github仓库/frontend/src/utils/markdown.js)，`ChatMessage.vue` 助手正文改 `v-html` 渲染并加配套 markdown 样式。

## BUG-009 · 膳食报告面板弹「接口不存在」

- **现象**：点「膳食报告」面板，浏览器弹「接口不存在，请检查后端服务」。
- **层面**：前端错误处理。
- **根因**：后端 `GET /nutrition/report` 用 `BizError(NOT_FOUND, http_status=404)` 表示「暂无报告」（body 里 `code=1004`），而前端 http.js 的错误处理器只看 HTTP 状态、404 一律弹「接口不存在」，没识别 body 里的业务码 1004（应渲染空态）。
- **状态**：已闭环。
- **修复**：[frontend/src/api/http.js](github仓库/frontend/src/api/http.js) 错误处理器优先按响应体业务码处理（1004→null 空态、2005/1002/其余业务码同成功分支）。

## BUG-010 · Agent 连库默认账号 `diet_app` 是 NOLOGIN，照抄 `.env.example` 连不上库

- **现象**：新环境（或本地重新起 Agent）时，Agent 服务（8001）的 rule_engine 连不上数据库，配餐 / 生成链路直接失败。
- **层面**：Agent 配置。
- **根因**：[agent/.env.example](github仓库/agent/.env.example) 与 [agent/config.py](github仓库/agent/config.py) 默认 `DATABASE_URL=postgresql+psycopg://diet_app:diet_app_dev@localhost:5432/diet_agent`；但 `diet_app` 是 [database/03_应用账号与权限.sql](github仓库/database/03_应用账号与权限.sql) 建的 **NOLOGIN 权限组**（不能登录），后端/rule_engine 必须用 `diet_backend` 登录账号（见 [backend/scripts/grant_backend_login.sql](github仓库/backend/scripts/grant_backend_login.sql)）。`docs/联调环境说明.md` 第 151 行也明确写了要用 `diet_backend`，但模板与代码默认值没跟着改。
- **状态**：已闭环（`agent/.env.example` 与 `agent/config.py` 默认 `DATABASE_URL` 已改为 `diet_backend:diet_backend_dev`）。

## BUG-011 · 「当前规划」面板永远空态（`normalizeCurrentPlan` 认不出真后端结构）

- **现象**：点「确认方案」后，侧边栏「当前规划」无任何返回，一直显示空态。
- **层面**：前端 schema 适配。
- **根因**：[frontend/src/utils/schema.js](github仓库/frontend/src/utils/schema.js) 的 `normalizeCurrentPlan` 用 `has_plan` 字段判断有无方案；但真后端 `GET /meal-plan/current` 返回的 `_serialize_plan` **没有 `has_plan`**（只有 `meal_plan_id`），故 `hasPlan` 恒 false。且槽位结构不一致：Mock 是扁平 `dish_names/dish_ids/kcal`，真后端是 `slots[].candidates[]`。
- **状态**：已闭环。
- **修复**：`normalizeCurrentPlan` 改为以 `meal_plan_id` 判有无方案；槽位优先走标准 `normalizeSlot`（candidates 结构，含菜名/热量），Mock 扁平结构保留兼容分支（待 Mock 对齐后端结构后删除）。

## BUG-012 · 系统代理导致 localhost 互调 502

- **现象**：后端调 Agent、Agent 调后端时返回 HTTP 502（「Agent 服务返回 HTTP 502」），但 Agent 健康检查正常、curl 直连 200。
- **层面**：后端 / Agent 出站请求。
- **根因**：httpx / requests 默认 `trust_env=True`，会读 Windows 系统代理（如 Clash/V2Ray 的 `127.0.0.1:7897`），把 `127.0.0.1:8001` 这类本机地址也路由到代理 → 502。curl 对 localhost 默认绕过代理，所以单测没暴露。`trust_env=False` 后直接 200。
- **状态**：已闭环。
- **修复**：后端 [chat.py](github仓库/backend/app/routers/chat.py) 调 Agent 用 `httpx.Client(trust_env=False)`；Agent [backend_client.py](github仓库/agent/backend_client.py) 改 `requests.Session()` 并 `trust_env=False`。只影响本机互调，外呼 DeepSeek/embedding 仍走代理。

## BUG-013 · 「为什么这样搭」解释请求超时

- **现象**：问「为什么这样搭」时后端返回「Agent 服务不可达（ReadTimeout）」兜底，看不到解释。
- **层面**：超时配置 / 模型性能。
- **根因**：解释分支要让 DeepSeek（`deepseek-v4-pro`）生成大段带依据的正文，实测耗时约 60s，正好顶到后端 `AGENT_TIMEOUT_S=60`。
- **状态**：已闭环（`backend/.env` 的 `AGENT_TIMEOUT_S` 调大到 120）。
- **备注**：模型响应偏慢值得观察，后续可考虑换更快模型或精简解释 prompt。

---

## BUG-014 · 点早餐餐位「换一换」→ Agent 报「没找到对应的餐位」

- **现象**：餐卡里点早餐餐位的「换一换」，前端自动发 `更换早餐候选`，Agent 回复「没找到对应的餐位」。
- **层面**：Agent 槽位查找。
- **根因**：[agent/agent.py](github仓库/agent/agent.py) 的 `_find_slot` 仍按旧 `rule_engine_bridge` 结构找槽位——遍历 `plan["days"][]["slots"]`，用 `label`（「早餐」）或 `meal_type`（英文 `breakfast`）匹配；但真后端 `_serialize_plan`（v1.2）返回的是**顶层 `slots`（无 `days` 包装）**，且 `meal_type` 是**单字中文「早/午/晚」**、没有 `label`。于是 `plan["days"]` 恒为空 → 找不到 → 返回「没找到对应的餐位」。
- **附带缺陷**：换候选分支把 `bc.swap_candidate` 的**部分返回**（只有 `candidate` + `macro_delta`，没有 `slots`）直接 `st["current_plan"] = updated_plan`，会覆盖掉完整方案，后续餐卡/再换候选都拿不到槽位。
- **状态**：已闭环。
- **修复**：
  1. `_find_slot` 重写为遍历「顶层 `slots` + `days[].slots`」两种结构，餐次先归一成单字「早/午/晚」再比对（`早餐/breakfast/早` → `早`）。
  2. 换候选先调 `bc.swap_candidate`（只落库），再按 id 走 `bc.get_meal_plan()`（新增，GET `/meal-plan/{id}`）拉完整方案刷新内存态；回执菜名/热量从 `selected_candidate.dishes` / `macro_estimate.kcal` 取。

## BUG-015 · 「选用候选」匹配不上（后端候选无 `name` 字段）

- **现象**：单餐卡片点某个候选，Agent 报「我没听清是哪个候选」（或选错候选）。
- **层面**：Agent 候选匹配。
- **根因**：[agent/agent.py](github仓库/agent/agent.py) 的「选用」分支用 `c["name"] in message` 匹配候选；但后端 `_serialize_candidate` **没有 `name` 字段**（菜名在 `dishes[].name`），`c["name"]` 直接 KeyError。且 `name` 是消息全文、候选名是菜名串，本就不是同一口径。
- **状态**：已闭环（与 BUG-014 同批，共享其 `_find_slot` 与「换完再按 id 拉完整方案」两处修复）。
- **修复**：新增 `_candidate_name()` 用 `dishes[].name` 拼菜名串（与前端 `candidateView.name` 同构），匹配逻辑改为「菜名串完整出现在消息里、取最长命中」——避免单菜子集（如「米饭」）抢走「米饭 + 清炒西兰花」；选定后同样多传 `candidate_id` 调 `swap_candidate` 再 `get_meal_plan` 拉完整方案。

## BUG-016 · 确认方案后聊天里的食材清单卡片为空（`_shopping_list` 读错结构）

- **现象**：点「确认方案」后，聊天里弹的食材清单卡片显示「共 0 项 / 清单还是空的」。
- **层面**：Agent 清单来源。
- **根因**：[agent/agent.py](github仓库/agent/agent.py) 的 `_shopping_list` 遍历 `plan["days"]`、读 `slot["dishes"]`（旧 rule_engine_bridge 结构）；但真后端 `_serialize_plan` 是**顶层 `slots`**，且真实食材清单本就在 `fix` 时由后端 `_shopping_items` 按食材级算好、写进 `app.shopping_list`。Agent 本地重算拿不到任何 day → 空清单。
- **状态**：已闭环。
- **修复**：`_shopping_list` 改为直接调后端 `GET /api/shopping-list?meal_plan_id=`（新增 `backend_client.get_shopping_list`），Agent 不再本地重算；`shopping_list_block` 透传 `total_items` / `meal_plan_id`。顺手修正了新增 `get_meal_plan` 漏 `/api` 前缀的问题（后端所有路由都挂 `/api`）。

## BUG-017 · 「生成报告」走离线预览 / 报告卡片被丢弃

- **现象**：点「生成周/月膳食报告」，聊天里看不到报告卡片（或只见离线预览文案）。
- **层面**：Agent 报告链路。
- **根因**（三处）：
  1. [agent/agent.py](github仓库/agent/agent.py) 用 `plan.get("plan_id")` 取方案 id，但后端字段是 `meal_plan_id`，恒取到空串 → `str(plan_id).isdigit()` 恒 false → 永远走「离线预览」分支，调不到真 `nutrition_analysis`。
  2. [agent/blocks.py](github仓库/agent/blocks.py) 的 `report_block` 发 `type:"nutrition_report"`，但后端 [chat.py](github仓库/backend/app/routers/chat.py) 的 `_ARTIFACT_TYPE_MAP` 只认 `"report"→"nutrition_report"`，未知 type 被直接丢弃。
  3. Agent 侧 `_report_dict` 把后端完整报告转成残缺「视图」（`macro.segments` 空、无 `completeness`/`daily_trend` 等），和前端 `normalizeReport` 期望的原始结构对不上。
- **状态**：已闭环。
- **修复**：报告分支改取 `meal_plan_id` 调 `bc.nutrition_analysis`，把后端 `/nutrition/analysis` 的完整方案级报告**原样透传**给 `report_block`；`report_block` 改为 `type:"report"`（映射成契约 `nutrition_report`），删除废弃的 `_report_dict`，渲染交给前端 `normalizeReport`。

## BUG-018 · 同一时间段多次确认/固定不同方案 → 膳食报告重复累计

- **现象**：用户在同一个日期段内多次「确认/固定」不同方案（如 11-17 固定一份一日三餐后，又生成并固定另一份 11-17 的方案），周/月膳食报告把这几份的摄入叠加起来，热量/微量翻倍、`daily_trend` 同一天出现多份餐位。
- **层面**：后端报告聚合 + 固定接口 + 数据库函数 + Agent 确认流。
- **根因**（三处叠加）：
  1. [backend/app/routers/mealplan.py](github仓库/backend/app/routers/mealplan.py) 的 `fix_plan` 只挡「同一份方案重复固定」，**不检查用户是否已有另一份覆盖同日期段的 fixed 方案**，于是同日期段多份 `status='fixed'` 方案并存。
  2. [backend/app/routers/nutrition.py](github仓库/backend/app/routers/nutrition.py) 的 `_load_selected_window` 把窗口内**所有** fixed 方案的餐位无脑求和，不去重。
  3. 库函数 `app.recent_micro_balance`（[database/02_数据库结构…合并版.sql](github仓库/database/02_数据库结构_diet_agent_v1.2r2_合并版.sql)）同样对窗口内全部 fixed 方案求和，供 `_rebuild_hints` 回溯判断，也跟着叠加。
- **状态**：已闭环（代码 + 迁移已应用并重启后端/Agent，待浏览器复验）。
- **修复**（三层：止血 → 源头 → 前端标签）：
  1. **止血（报告去重）**：`_load_selected_window` 与 `app.recent_micro_balance` 改为对同一餐位 `(slot_date, meal_type, display_order)` 只取 `fixed_at` 最新一份（`DISTINCT ON … ORDER BY … fixed_at DESC`）。
  2. **源头（固定冲突检测 + 取代）**：`fix_plan` 新增 `replace` 入参；固定前用 `_overlapping_fixed_plans` 按「同一天同一餐次」检测重叠的 fixed 方案，并区分「完全覆盖 / 部分重叠」——无 `replace` 时返回 `2005/409`，提示里如实说明「整份作废」或「部分重叠、其余日期一并失效」，带 `replace=true` 时把旧方案标记为 `superseded`。Agent 确认流遇到 2005 追问「回复『替换』覆盖 / 回复『取消』保留」，并新增 `cancel` 意图。
  3. **数据模型**：迁移 [database/39_方案取代与报告聚合去重_v1.2r3.sql](github仓库/database/39_方案取代与报告聚合去重_v1.2r3.sql) 新增 `meal_plan.superseded_at / superseded_by_plan_id`、状态枚举加 `superseded`、放行 `fixed → superseded` 守卫流转。
  4. **前端**：`STATUS_LABELS` 补 `superseded: '已取代'`，`.status-tag.superseded` 样式；后端 `list_plans` 的 status 过滤枚举补 `superseded`。
- **备注**：旧方案 `shopping_list` 行仍留在库内（不影响展示，当前规划只读最新 fixed）；如需清理可后续加「取代时同步失效旧清单」。

## BUG-019 · 对话 markdown 正文块间空行（pre-wrap 泄漏到 AI 气泡）

- **现象**：AI 回复的 markdown 正文里，每个段落 / 小节标题之间都多出一行空行，标题上下尤其明显，整体稀疏、观感差。
- **层面**：前端渲染（CSS）。
- **根因**：[base.css](github仓库/frontend/src/styles/base.css) 给 `.msg.ai .bubble` 设了 `white-space: pre-wrap`（本意是给**用户**纯文本气泡保留换行），但 AI 气泡里是 `v-html` 渲染的 markdown HTML。markdown-it 输出的每个块（`<p>` / `<h3>`）之间夹着一个 `\n` 文本节点，正常 `white-space: normal` 下会被折叠，`pre-wrap` 却把它保留成可见空行 → 块与块之间凭空多一行。
- **状态**：已闭环。
- **修复**：
  1. [ChatMessage.vue](github仓库/frontend/src/components/chat/ChatMessage.vue) 给 `.md` 加 `white-space: normal`，折叠块间换行；
  2. 补段落间距：`.bubble .md :deep(p) { margin: 0 0 8px }`（提升优先级，压过 base.css 的 `.msg.ai .bubble p{margin:0}`），标题间距 `12px 0 4px`；
  3. 兜底：[markdown.js](github仓库/frontend/src/utils/markdown.js) 新增 `normalizeSpacing`（裸小节标题「能量/蛋白…」提升为 `##`/`###`、连续 3+ 空行压成 1 段、去行尾空格）。

## BUG-020 · 周餐卡 21 个餐位平铺、不按天分组（Agent 丢 slot_date）

- **现象**：发「生成一周食谱」后，对话里的餐卡把 7 天 × 早/午/晚共 21 个餐位连续平铺输出，分不清对应哪一天，长文本观感差；前端本已写好的「按天折叠」周餐卡（`week-list`）一直没被触发。
- **层面**：Agent blocks.py（字段丢失）→ 前端分组退化。
- **根因**：[agent/blocks.py](github仓库/agent/blocks.py) 的 `_slot_view` 转 `meal_card` 时**丢掉了 `slot_date` / `display_order`**，且 `meal_card_block` 硬写 `days: []`。前端 [schema.js](github仓库/frontend/src/utils/schema.js) 的 `groupDays` 按 `slot_date` 分组时全部落到空日期 → 21 餐位归成「1 天」→ `isMultiDay=false` → 走「一日三餐」平铺分支。
- **状态**：已闭环。
- **修复**：
  1. `_slot_view` 补齐 `slot_date` / `display_order` / `target_macro` 透传，前端 `groupDays` 得以按天分组、触发折叠列表；
  2. [MealCardBlock.vue](github仓库/frontend/src/components/renderer/blocks/MealCardBlock.vue) 折叠默认展开「今天」（找不到回退第一天）；
  3. [schema.js](github仓库/frontend/src/utils/schema.js) `groupDays.is_today` 由 `new Date().toISOString()`（UTC）改为本地 `todayIso()`，修正 UTC+8 凌晨「今天」判定偏移。

## BUG-021 · 「当前规划」点「查看膳食报告」只切面板、无动作

- **现象**：「当前规划」面板点「📊 查看这份方案的膳食报告 →」，右侧只切到「膳食报告」面板，什么都没发生——已有方案级复盘不会弹出，没有复盘也不会触发对话生成。
- **层面**：前端交互。
- **根因**：[CurrentPlanPanel.vue](github仓库/frontend/src/components/tools/panels/CurrentPlanPanel.vue) 的 `openReport()` 只有一句 `panel.open('report')`，把面板切成「膳食报告」；但该面板的 `/nutrition/report/list` 只返回 week/month/custom 周期报告（[nutrition.py](github仓库/backend/app/routers/nutrition.py) `report_type IN ('week','month','custom')`），**不含方案级复盘**（`report_type='plan'`），所以跳过去匹配不到任何东西。
- **状态**：已闭环。
- **修复**：`openReport()` 改为：先用 `fetchReport({ mealPlanId })` 读方案级复盘 → 有则直接 `ui.reportPayload + ui.reportOpen` 弹报告弹窗；无且方案未固定则提示「先确认方案」（draft/candidates 无已选候选，无法分析）；无且已固定则 `chat.send(PHRASE.report)`（「生成方案膳食报告」，对话为唯一入口）走 Agent 生成并落库。按钮加「正在查看…」loading/禁用态。

## BUG-022 · 微量「超标」误判：超过推荐量 100% 即判超标（应对 UL 判）

- **现象**：膳食报告里某微量只要摄入超过推荐量（RNI/AI）的 100% 就被标「超标」。例如钙成人 RNI 800mg，吃到 900mg 就红字「超标」——但 UL 是 2000mg，900mg 完全在安全范围。
- **层面**：后端营养判定 + 前端展示。
- **根因**：[nutrition.py](github仓库/backend/app/routers/nutrition.py) 的 `_micro_summary` 用 `covered > 100`（占推荐量百分比 >100%）判「超标」；而「超标」的正确口径是超过**可耐受最高摄入量（UL）**。且 `_load_reference` 的 SELECT 把库里的 `ul_value` 字段丢了（[core.nutrient_reference](github仓库/database/02_数据库结构_diet_agent_v1.2r2_合并版.sql) 本来就存了 DRIs 2023 的 UL）。前端 `microView` 的备注「已超 X」也是拿 `gap = intake - target`（对推荐量）算的，语义同样错。
- **状态**：已闭环。
- **修复**：
  1. `_load_reference` 补选 `ul_value`；
  2. `_micro_summary` 判定改为：`intake > ul`（且 `ul` 非空）才判「超标」，`covered>=80` 判「达标」，否则「不足」；输出补 `ul` 字段。B1/B2 等无 UL 的微量因此不再可能被误判超标；
  3. 前端 [schema.js](github仓库/frontend/src/utils/schema.js) `microView` 的备注改为由 `status` 驱动：超标显示「超过每日上限 X」，不足显示「还差 X」，其余「已达标」，并把 `ul` 透传；
  4. `_achievement`（报告达标率环）的单日「达标」由 `v >= target`（≥100%）统一为 `v >= 0.8*target 且未超 UL`，与 `_micro_summary` 口径一致。

## BUG-023 · 一餐搭配「选项切换」不灵敏：点候选要等几秒或点多次才切

- **现象**：单餐搭配卡片里点 2~3 个候选之间的切换，总要过一会才真正切换，或者要点好几下才有反应。
- **层面**：前端交互 + Agent 叙事链路（跨三层）。
- **根因**（两点叠加）：
  1. **叙事 LLM 白等**：点候选走 [MealCardBlock.vue](github仓库/frontend/src/components/renderer/blocks/MealCardBlock.vue) 的 `pickCandidate` → `chat.silentAction` → 同一套 `/api/agent/chat` SSE 流。[agent/main.py](github仓库/agent/main.py) 的 `_stream` **永远先让 DeepSeek 流式生成一段叙事正文**（`stream_reply` 真调 LLM，数秒），之后才发 `meal_card`、最后 `done`。而前端 `silentAction` 只消费 `meal_card`、正文被直接丢弃，却仍要**等正文流完才收到 `done`**、才把 `sending` 置回 false——真正的切换被叙事拖慢数秒。
  2. **等待期点击被静默吞掉**：等待期间 `chat.sending=true`，[pickCandidate 的守卫](github仓库/frontend/src/components/renderer/blocks/MealCardBlock.vue#L200) 直接 return，无任何反馈，表现为「点好多次才切」。
- **状态**：已闭环。
- **修复**：给静默按钮动作（换一换 / 选用 / 确认）加 `silent` 标记，一路透传 `前端 → 后端 → Agent`，让 Agent 跳过 LLM 叙事、直接落卡 + done，把数秒压到几十毫秒；同时前端对「点已选中候选」做无操作兜底，避免误弹「选用失败」。
  1. 前端 [agent.js](github仓库/frontend/src/api/agent.js) `streamChat` 支持 `silent`，请求体带 `silent:true`；
  2. 前端 [chat.js](github仓库/frontend/src/stores/chat.js) `silentAction` 传 `silent:true`；
  3. 后端 [chat.py schema](github仓库/backend/app/schemas/chat.py) `ChatRequest` 增 `silent: bool = False`，[chat.py 路由](github仓库/backend/app/routers/chat.py) 透传给 Agent；
  4. Agent [main.py](github仓库/agent/main.py) `AgentChatRequest` 增 `silent`，`_stream` 在 `silent` 时跳过叙事段，直接发 block + done；
  5. 前端 [MealCardBlock.vue](github仓库/frontend/src/components/renderer/blocks/MealCardBlock.vue) `pickCandidate` 对已选中候选直接 return。
- **备注**：普通对话（打字/固定话术走 `send`）不传 `silent`，叙事照旧，不受影响；`silent` 缺省 false，对既有调用方向后兼容。

## BUG-024 · Agent 生成方案后引导「去当前规划面板看餐卡」，但当前规划存的是已固定方案

- **现象**：生成一日三餐/单餐后，Agent 正文会写「你可以到右侧『当前规划』面板看看餐卡」；但「当前规划」面板语义是**已固定（fixed）的方案**，刚生成的候选（candidates/draft）只在对话里的餐卡呈现，不在「当前规划」面板——引导与实际不符。
- **层面**：Agent 叙事引导文案。
- **根因**：[agent.py](github仓库/agent/agent.py) 生成分支的 `context` 引导行写死「右侧「当前规划」面板可查看」；换候选分支的 `fallback` 也带「(可在面板中查看当前规划)」。这两句把「待确认候选」误指到「当前规划」面板，LLM 照抄进正文。
- **状态**：已闭环。
- **修复**（改 [agent.py](github仓库/agent/agent.py) 三处文案，让 LLM 引导与真实闭环一致）：
  1. 生成分支引导改为「餐卡已在对话里展示，可直接点「换一换」换候选；点「确认方案」固定后，才会同步到右侧「当前规划」面板并生成食材清单」；
  2. 换候选兜底改为「餐卡已更新，可以继续换，或点「确认方案」固定」（去掉「可在面板中查看当前规划」）；
  3. 闲聊兜底「功能面板可在左下角菜单中找到」→「右侧工具栏可打开食材清单、当前规划、膳食报告等面板」（面板本就在右侧图标栏）。
- **备注**：仅改叙事文案，不涉及后端 `current_plan` 返回逻辑。若后续想进一步收紧语义（`/meal-plan/current` 只回 fixed、不回 candidates），可作为独立项处理，与本次 Agent 引导修复解耦。

## BUG-025 · 点「换一换」右侧工具栏整体刷新（换候选只改草稿却触发四面板重载）

- **现象**：在餐卡点「换一换」或「选用候选」后，右侧工具栏四个面板（食材清单/当前规划/历史方案/膳食报告）一起刷新（骨架屏闪一下）。
- **层面**：前端面板刷新触发。
- **根因**：[chat.js](github仓库/frontend/src/stores/chat.js) 的 `silentAction`（换候选/选用专用）在结束时调用 `panel.bump()` → `revision++`；四个面板都 `watch(() => panel.revision, load)`（[CurrentPlanPanel.vue](github仓库/frontend/src/components/tools/panels/CurrentPlanPanel.vue#L255) 等），于是每次换候选都整体重载。但换候选只改**草稿候选的选中项**，不改固定方案、食材清单、历史方案列表、膳食报告，没必要刷新这四块。
- **状态**：已闭环。
- **修复**：
  1. [chat.js](github仓库/frontend/src/stores/chat.js) `silentAction` 去掉 `panel.bump()`（换候选/选用不再触发全局刷新）；
  2. [CurrentPlanPanel.vue](github仓库/frontend/src/components/tools/panels/CurrentPlanPanel.vue) 面板自己的「换一换」按钮，换完后本地 `load()` 刷新自身（因为它可能正在展示这份「待确认」草稿，需要看到新候选）。
- **备注**：`send()`（生成/确认/报告）仍保留 `panel.bump()`，这些动作确实改了固定方案/清单/历史/报告，需要刷新。若后续把 `/meal-plan/current` 收紧成只回 fixed，面板里「待确认」草稿与换一换按钮都会消失，本项语义将彻底一致。

## BUG-026 · 症状咨询检索为空仍追加「由文献库提供参考」假出处

- **现象**：用户问症状（如「乏力 掉发」），Agent 回复末尾固定带「(注：以上信息由文献库提供参考，不可替代专业医疗诊断…)」；但后端 `reverse-nutrition` 实际返回 `items:[]`（未检索到任何文献）。用户追问「你的知识库检索干嘛用」，LLM 只能自曝「我这边没有文献检索这回事」——「文献库提供参考」成了无中生有的假出处。
- **层面**：Agent 叙事（反向营养分支）。
- **根因**：[agent.py](github仓库/agent/agent.py#L1152-L1171) `reverse_nutrition` 分支把 `suffix` 写死成「由文献库提供参考」，无论 `content` 是否为空都追加；而后端 [agent.py](github仓库/backend/app/routers/agent.py#L160-L175) 的反向营养只走 `_search_knowledge` 关键词兜底、未接 `symptom_nutrient_map`，对「乏力 掉发」这类症状命中为空。于是「声称有出处」与「实际无检索」矛盾，直接违反「可溯源 / 零编造」铁律。
- **状态**：已闭环。
- **修复**：`reverse_nutrition` 分支按 `content` 是否为空分流 `suffix`——有检索线索才写「以上营养线索来自知识库检索」；为空写「未检索到具体文献，以上为通用营养学常识」；两者都保留「仅供参考、不构成诊断、建议就医」。
- **备注**：根治还需 IMP-036（`symptom_nutrient_map` 接线）——接线后症状咨询能真正命中映射、拿到真实来源，本项的后缀分流才不会「永远走空分支」。

## BUG-027 · RRF 混合检索丢 source/source_id（可溯源落空）

- **现象**：`POST /api/agent/rag-query` 返回的每条 `RagItem` 的 `source`/`source_id` 均为 `null`，而库内 `knowledge.knowledge_doc` 43/43 都有 `source`（如 `营养素知识库/nutrients.json`）。知识问答拿不到出处，前端 / LLM 无法「标注来源」。
- **层面**：后端检索 + DB 检索函数。
- **根因**：[14_RAG向量化_v1.2r1.sql](github仓库/database/14_RAG向量化_v1.2r1.sql#L149-L158) 的 `knowledge.search_documents` 返回列只有 `knowledge_doc_id/title/category/content/score/vector_rank/text_rank/vector_similarity`，**不含 `source`/`source_id`**；[agent.py](github仓库/backend/app/routers/agent.py#L104-L150) `_search_hybrid` 构造 `RagItem` 时也未映射这两列。关键词兜底 `_search_knowledge` 有 source，但实际走的是混合路径，于是来源被丢。
- **状态**：已闭环（11-19 Anna 修复 `4f6c937`，测试 LIVE L-05 PASS 后关闭 issue #12）。
- **修复**：采用应用层回查方案——`_search_hybrid` 拿到 `knowledge_doc_id` 列表后，一次 `SELECT source, source_id FROM knowledge.knowledge_doc WHERE knowledge_doc_id IN (...)` 补齐，不 DROP/CREATE 函数、不动权限、无需随部署批迁移；回查异常只置空 source 并打 warning，不拖挂检索主链路。keyword_fallback 分支本就带 source，两路行为一致。
- **验收**：`4f6c937` 代码验收 PASS；新域名 `retail-sixth-beauty-illustration.trycloudflare.com` 上 `verify_gd3_live.py` 的 L-05（query 换「主食」、missing 按 `kind=="doc"` 过滤）doc=5、source 缺失 0；G-D3 LIVE 7/7、G-D 15/15、G-D2 4/4。

## BUG-028 · 过敏原「海鲜」「麸质」勾选后不拦截对应菜品（词表映射缺口）

- **现象**：档案页过敏原选项只有 6 个——`['花生','牛奶','海鲜','鸡蛋','麸质','无']`（[ProfileModal.vue](github仓库/frontend/src/components/profile/ProfileModal.vue#L231)），但数据侧 `core.ingredient.allergens` 用的是细标签（`鱼类 / 软体贝类 / 甲壳类水产 / 小麦 / 麸质 / 大豆 / 芝麻 / 牛奶 / 鸡蛋`）。结果是：
  - 勾「**海鲜**」→ 鱼类、软体贝类、甲壳类水产三类菜**全部放行**（清蒸黄花鱼、白灼鱿鱼、白灼虾都能进方案）；
  - 勾「**麸质**」→ 标签写作「小麦」的菜（白馒头 / 切片面包 / 清汤面 / 疙瘩汤）放行；
  - 勾「花生 / 牛奶 / 鸡蛋」正常。
- **实测**（离线纯函数，零 DB）：9 组「勾选 × 菜品标签」对照，**5 组不拦截**——海鲜→鱼类、海鲜→软体贝类、海鲜→甲壳类水产、麸质→小麦、小麦→麸质（前三条是真实用户路径，「小麦」不在前端选项里）。
- **层面**：规则引擎硬过滤（后端）。
- **根因**：[candidates.py](github仓库/backend/app/services/rule_engine/candidates.py#L77-L85) 的 `aliases` 是**函数内硬编码字典**，只有 11 条：`鱼→鱼类、牛奶→牛奶、乳制品→牛奶、奶→牛奶、蛋→鸡蛋、虾→甲壳类水产、蟹→甲壳类水产、贝类→软体贝类、大豆→大豆、黄豆→大豆、花生→花生`。
  - 缺「海鲜」这一**一对多**映射（一个用户选项对应三个数据标签）；
  - 缺「麸质 ↔ 小麦」双向映射，而两种写法在库内并存（DB 食材表用「麸质」，`meal_templates` 主食模板 055/062/063/065 标「小麦」）。
  - 兜底的 `allergen in name_blob`（菜名/配料名命中）救不了：菜名里不会出现「海鲜」「麸质」这两个词。
- **状态**：已修（2026-11-19）。
- **修复**（采纳建议 A）：`candidates.py` 内联 `aliases` 字典升级为模块常量 `ALLERGEN_ALIASES: dict[str, set[str]]`（一对多），`hard_filter_reasons` 匹配改为「用户选项 canonical 集合 ∩ 菜品 strict_allergens 展开集合」交集非空即命中；`海鲜 → {鱼类,软体贝类,甲壳类水产}`，`麸质 ↔ 小麦` 双向。测试 [test_rule_engine_unit.py](github仓库/backend/tests/test_rule_engine_unit.py) 两组 xfail 已摘除、转正式回归用例。9 组对照全部拦截通过。
- **备注**：**P1（过敏安全）**。前端 6 个选项里原 1 个（海鲜）完全失效、1 个（麸质）部分失效，用户是海鲜/麸质过敏时会被推上致敏菜。后续数据侧若新增过敏原写法（如「含麸质的谷物」），须同步维护 `ALLERGEN_ALIASES` 这张表。与 BUG-026/027 无耦合。

## 附：元问题（非单个 bug）

本轮 6 个缺陷几乎同一病根——**后端/Agent 实际吐出的字段与「输出契约 v1.2」约定对不上**（字段缺失、字段名不一致、类型不一致）。建议 Agent 岗 + 后端岗按契约逐字段对一遍，否则还会继续冒出「食材清单缺名」「报告字段错位」等同款问题。

## BUG-029 · 停止生成后消息上方残留「正在生成配餐方案」状态

- **现象**：对话流式生成中，点输入框的「停止生成」后，AI 气泡上方仍保留带脉冲圆点的「正在生成配餐方案」思考步骤条，与下方的「已停止生成」提示矛盾，看起来像还在生成。
- **层面**：前端（对话流渲染）。
- **根因**：[chat.js](github仓库/frontend/src/stores/chat.js) 的 `send()` 在 `AbortError`/`CANCELED` 分支只把 `aiMsg.status` 置为 `'stopped'`，未清空 `aiMsg.thinking`；而 [ChatMessage.vue](github仓库/frontend/src/components/chat/ChatMessage.vue#L14-L16) 的思考步骤条只判断 `message.thinking` 是否有值，不看 `status`，导致停止后仍显示上次 `status` 事件写入的阶段文字。
- **状态**：已修（2026-11-20）。
- **修复**：`AbortError`/`CANCELED` 分支补 `aiMsg.thinking = ''`；另在流正常结束但未收到 `done` 事件的兜底分支同样清空 `thinking`，杜绝同类残留。

## BUG-030 · 确认方案遇同期固定方案冲突时，只弹裸警告、无「替换/取消」按钮

- **现象**：已有同期 fixed 方案时，点餐卡「确认方案」按钮 → 只弹一条 ElMessage toast「已有覆盖同期的已固定方案（id=85）…」，没有可点的「替换/取消」，用户看起来像「被卡住、无法修改」。
- **层面**：Agent 静默路径 + 前端卡片确认 + 后端文案。
- **根因**：餐卡「确认方案」走 `chat.silentAction`（静默动作）。Agent [main.py](github仓库/agent/main.py) 的静默守卫只认 `meal_card`，而 confirm 遇到 2005 冲突时 Agent 返回的是 `quick_actions`（替换/取消）块，被守卫判 `matched=False` 后降级成 `error(2003)`，只透传 `text`、把 `quick_actions` 块丢弃；前端 `silentAction` 收到 error → throw → `onConfirm` 用 ElMessage 弹裸文案。同时文案泄露内部主键 id（IMP-031 已记）。
- **状态**：已修（2026-11-20）。
- **修复**：
  1. [main.py](github仓库/agent/main.py) 静默守卫：confirm 冲突（结果含 `quick_actions`）时保留 2005 码而非 2003，供前端区分。
  2. [chat.js](github仓库/frontend/src/stores/chat.js) `silentAction` 透出 `errorCode`，抛错时挂到 `err.code`。
  3. [MealCardBlock.vue](github仓库/frontend/src/components/renderer/blocks/MealCardBlock.vue) `onConfirm`：捕获 `code===2005` 时退回对话路径 `chat.send('确认当前方案')`（不带 context，避免后端把 `current_plan` 当聊天卡下发），并加 `confirming` 状态让按钮在确认/追问期间禁用，避免重复点。
  4. [mealplan.py](github仓库/backend/app/routers/mealplan.py) 冲突文案去掉内部 id，改用户向表述（对应 IMP-031）。
  5. [agent.py](github仓库/agent/agent.py) 冲突追问定位：confirm 遇 2005 时把目标方案 id 记进会话态 `_pending_confirm_plan_id`，`_operation_plan` 在多方案且无 context 时用它兜底定位；「替换/取消」命中后清除。这样裸话术「替换」在多方案场景也能定位。
  6. [ActionsBlock.vue](github仓库/frontend/src/components/renderer/blocks/ActionsBlock.vue) 「替换/取消」改一次性按钮：点过一次即禁用，避免重复点出第二次追问。
  7. [agent.py](github仓库/agent/agent.py) 「替换」成功后的回复改**确定性文案**（`text` 而非 LLM `narration`）：此前「替换」这个裸词交给 LLM 叙事，会被误读成「待确认替换范围」再追问一次，反而诱导用户继续输入「替换午餐」撞上「已固定不可改」。现在直接回「已确认，方案已生效。已取代同期的旧方案。」+ 固定后的餐卡。
- **备注**：能力本身一直都在（`replace=true` → 旧方案标 `superseded`），只是按钮路径先把选择入口吞了、再把方案定位丢了、最后把成功文案交给了容易跑偏的 LLM。修复后链路为：卡上「确认方案」→ 冲突 → 气泡出现「替换/取消」→ 点「替换」携带 Agent 记住的目标方案 id 完成取代并给出确定文案。

---

## BUG-031 · 早/晚能量占比 25/35 与规范 30/30 不符

- **现象**：默认三餐方案的早餐能量按日能量 25% 算、晚餐按 35%，而规范口径是「早 30% / 午 40% / 晚 30%」。早餐整体低估、晚餐高估 5 个百分点日能量。
- **层面**：规则引擎。
- **根因**：`backend/app/services/rule_engine/models.py:23` 写死 `DEFAULT_MEAL_RATIOS = {"早": 0.25, "午": 0.4, "晚": 0.35}`，与 `backend/app/services/rule_engine/targets.py:6` 的 docstring 及 CLAUDE.md §5「早 30%/午 40%/晚 30%」矛盾；`targets.py` 用该 ratio 推导各餐 kcal/蛋白/脂肪/碳水/油盐上限。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：改为 `{"早": 0.30, "午": 0.40, "晚": 0.30}`；确认 `targets.py` 与 `nutrition.py` 引用的是同一常量，避免再出现「注释一个口径、常量另一个口径」。

## BUG-032 · 缺钠(null)被当硬排除，候选被静默丢弃（违反 null≠0）

- **现象**：只要一道菜任一食材缺钠（`sodium_mg=NULL`），这道菜及其组合就被当硬失败整组丢弃，候选池缩小，极端时正餐/早餐出现「无合法候选」；同时 `_score` 里的 `oil_salt_unknown` 告警分支永远不可达（死代码）。
- **层面**：规则引擎（候选生成）。
- **根因**：`backend/app/services/rule_engine/candidates.py:213-220` 的 `hard_budget_failures` 对「任一 `sodium_mg` 为 None」直接返回 `total_sodium_unknown` 硬失败；`candidates.py:452` 与 `:541` 在打分前 `if hard: continue` 整体淘汰。SQL 层对钠做 NULL 传播（一道菜一个食材缺钠→整道菜 `sodium_mg=None`），所以命中面很大。这与函数自身 docstring「Missing values stay unknown. Reject only if known values already exceed the limit」直接矛盾，也违反铁律「null≠0（未知不是 0，更不是可安全排除）」。
- **状态**：已修（2026-11-21 代码审查发现并修复）。
- **修复建议**：钠缺失不产生硬失败，改为进入 `_score` 的 `oil_salt_unknown` 告警分支（提示「钠数据不完整」）；仅当**已知**钠折算的盐当量超过油盐上限时才硬拒。同源问题也波及 `local_edit.py`（换一换对缺钠菜抛硬约束错误）。
- **修复（2026-11-21）**：四处「缺钠当硬排除」全部改为「仅已知钠超盐当量上限才硬拒」，缺钠走 `oil_salt_unknown` 告警——
  1. `candidates.py` `hard_budget_failures`：`any(sodium is None)` 分支删除，改为 `all(... is not None)` 时才判超限；
  2. `candidates.py` `_within`：`salt_equivalent is None` 不再追加 `total_sodium_unknown`；
  3. `meal_templates.py` `shortlist_combos`：`any(sodium is None) or 超限` 改为 `all(... is not None) and 超限` 才拒绝；
  4. `local_edit.py` `evaluate_portions`：硬拒元组删除已死产的 `total_sodium_unknown`。
  同步改 `test_v21_foundation.py`：删掉「缺钠→空候选」的旧断言，补「缺钠→非空候选 + `oil_salt_unknown` 标记」断言（对齐油缺失的既有行为）。全量后端测试 87 passed、无回归。**注**：实测当前 213 道菜钠数据已补齐（`44_确定不含营养素补零` 已覆盖），故本 bug 在现库为「潜伏」——但代码与 docstring/铁律一致化后，未来补录缺钠菜式不再被静默丢弃。

## BUG-033 · 跨日微量平衡查错时间窗口（查自身未来日期）

- **现象**：生成未来 1~7 天的方案时，`recent_micro_balance` 在新方案自身的（未来）日期上基本没有已固定餐 → 窗口总量≈0 → 7 种关键微量全被误判「不足」，并按 `window_days`（默认 7 天）目标放大缺口，触发无谓「补位」与误导性「低补」提示。
- **层面**：规则引擎（跨日微量平衡）。
- **根因**：`backend/app/services/rule_engine/pipeline.py:332-340` 把 `request.start_date / end_date` 直接当回溯窗口查；正确口径见 `backend/app/routers/nutrition.py:653`：`window_start = plan["start_date"] - timedelta(days=window_days - 1)`，即**往前回溯**而非查方案自身区间。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：`pipeline.py` 改按 `start_date - (window_days - 1)` 到 `end_date` 的回溯窗口查询；并核对 `window_days` 默认值与 `compute_balance` 的日目标乘数一致。

## BUG-034 · 清真/伊斯兰忌口漏排除猪肉「里脊/肉片/肉末」菜

- **现象**：宗教忌口含「清真/伊斯兰」的用户，仍会被推荐「彩椒里脊丝」「木耳炒肉片」「肉末豆腐」等以猪肉为原料的菜。
- **层面**：规则引擎（硬约束过滤）。
- **根因**：`backend/app/services/rule_engine/models.py:56-61` 的清真/伊斯兰关键词为 `("猪","五花","培根","火腿","香肠","腊肉","排骨","肉肠")`，刻意不含「肉」以免误伤牛羊，但因此漏掉以「里脊/肉片/肉末」命名的猪肉菜；`backend/app/services/rule_engine/candidates.py:109-114` 的 `hard_filter_reasons` 只对 `name_blob`（菜名+食材名）做子串命中，完全不看 DB 侧结构化的 `family` 字段。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：宗教过滤增加结构化兜底——优先用 DB 的 `family`/猪肉标签判断，或对「里脊/肉片/肉末」这类词结合食材成分做更细判定，避免「宁可漏杀猪肉、不可误杀牛羊」的现状反过来漏掉猪肉菜。

## BUG-035 · 已确诊疾病(confirmed_conditions)未参与候选硬过滤

- **现象**：档案 `conditions` 里有已确诊疾病（如糖尿病/痛风，status=confirmed）时，候选生成不受任何影响——疾病这条「硬排除」铁律在确定性层没有落地。
- **层面**：规则引擎（硬约束）。
- **根因**：`backend/app/services/rule_engine/targets.py:370/390` 只把 `confirmed_conditions` 写进 `Targets` 与 `condition_note`（文案），`candidates.py:92-135` 的 `hard_filter_reasons` 从未引用它；`repository.py` 也未加载 `v_production_condition_rules`（`routers/conditions.py` 暴露的疾病→营养素/食材规则）。
- **状态**：未修（2026-11-21 代码审查发现；**可能属 CLAUDE.md P1/P4 已知未实现口径，建议先定口径再修**）。
- **修复建议**：确认「疾病规则」是否在本轮范围；若是，接入疾病→营养素/食材排除规则到候选硬过滤。

## BUG-036 · 对话建档几乎必然 422 静默失败，宗教忌口/厨具从不落库

- **现象**：无档案用户说「我是男的，想减脂」这类不全信息 → LLM 对缺失字段填 0 → 后端 422 → `except: pass` 静默吞掉 → 用户只得到笼统追问「我还不太了解你的身体情况…」，而非按铁律 7 追问具体缺项；即使用户在对话里说了清真忌口/厨具，也不会入库。
- **层面**：Agent（对话建档）。
- **根因**：`agent/agent.py:1015-1038` 的 `_INTENT_SYSTEM` 让 LLM 对未提供字段填 `{"age":0,"height_cm":0,"weight_kg":0}`；`backend/app/schemas/profile.py:13-34` 的 `ProfileUpsertRequest` 要求 `gender(男/女)、age(10~100)、height_cm(120~220)、weight_kg(30~200)、goal_code` 全必填合法，填 0 必 422。同时 `upsert_profile` 从不传 `religious_ethical / cooking_equipment`，且 `_INTENT_SYSTEM` 的 profile 结构里根本没有这两项 → 硬约束信息丢失。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：① 建档缺项走 `needs_clarification` 追问具体缺项（铁律 7），不要静默吞 422；② `_INTENT_SYSTEM` 的 profile 结构补 `religious_ethical / cooking_equipment` 并透传后端；③ 后端 `except Exception: pass` 至少打日志、不吞错。

## BUG-037 · local_edit_only 误拦截「整份重新生成」请求

- **现象**：用户已有方案时说「重新生成一周食谱」或「重新安排今天三餐」→ 被错误拒绝为「你指定的是局部修改…我不会重新生成整份方案」。
- **层面**：Agent（意图路由）。
- **根因**：`agent/agent.py:876-878` 的 `local_edit_only` 只要消息含「重新(安排|生成|排)|重排|换成…」且对话里已有方案（`le.registry(state)`）就置 True，未排除「整份重新生成」这类全新方案请求；`regenerate_flow.py` 的 `is_new_plan_request` 已正确识别 `fresh=True`，但 `_tool_exec` 用的是重算的 `local_edit_only`，仍拦截。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：`local_edit_only` 排除 `is_new_plan_request`（fresh）的情况；或先判 fresh 再判 local_edit_only。

## BUG-038 · 报告自定义日期区间字段名不匹配（start/end vs period）

- **现象**：消息未命中正则报告关键词、由 LLM 归类 `report` 且 `scope="custom"` 时，`period_start=None` → 后端抛「custom 报告需提供 period_start 与 period_end」→ 用户看到「膳食报告生成失败」。
- **层面**：Agent（报告链路）。
- **根因**：`agent/agent.py:66-67` 的 `_INTENT_SYSTEM` 规定报告日期用 `start_date/end_date`，但 `agent.py:1241-1245` 的 report 分支读的是 `intent.get("period_start")/("period_end")`。正则路径返回 `period_start/period_end`，LLM 路径返回 `start_date/end_date`，两路径字段名不一致。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：统一字段名（正则路径与 LLM 路径对齐后再进 `period_analysis`）。

## BUG-039 · 单菜替换硬编码 allow_approximate=True，未经同意落库近似结果

- **现象**：用户点名换一道菜、唯一可行解是「营养近似」结果时，Agent 不经追问直接落库，违反「可明确同意近似结果后再试」与 data_quality 三态语义。
- **层面**：Agent（局部修改）。
- **根因**：`agent/local_edits.py:112-114` 无条件 `payload['allow_approximate'] = True`，与紧邻注释「Do not auto-authorize nutrition relaxation」矛盾；后端 `replace_dish` 只有在 `allow_approximate=True` 时才放过 `macro_range_relaxed` 近似候选。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：近似结果需先追问用户同意再落库（与 `regenerate_slot` 的「近似需同意」口径一致）。

## BUG-040 · swap_candidate 多日方案无法定位餐位（缺日期参数）

- **现象**：一周方案下用户说「把早餐换成清淡的」，LLM 调 `swap_candidate(meal_type=早餐)`，`_find_slot` 命中 7 个早餐 → 返回 None → 「没找到对应的餐位」。
- **层面**：Agent（槽位定位）。
- **根因**：`agent/agent.py:807-809` 的 `swap_candidate` 工具只带 `meal_type/prefer`，无日期或「第几天」参数；`agent.py:351-354` 的 `_find_slot` 在 `matches` 数 ≠1 时返回 None。同意图下 `regenerate_slot` 有 `day_index/slot_date` 定位，`swap_candidate` 缺失，定位能力不一致。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：`swap_candidate` 增加 `day_index/slot_date` 定位，与 `regenerate_slot` 对齐。

## BUG-041 · Agent 直连 /chat 异常只发 error 不发 done

- **现象**：直接消费 Agent 8001 `/chat` 的客户端若依赖 `done` 结束流，会在异常后挂起。当前前端经后端 `chat.py` 代理时被后端的 `finally` 补发 `done` 掩盖，故只在直连 Agent 时暴露。
- **层面**：Agent（SSE 协议）。
- **根因**：`agent/main.py:83-85` 的 `agent_task.result()` 抛异常时只 `yield error` 后 `return`，没有终止性 `done`；而同文件静默动作失败路径（`main.py:113-115`）是 `error+done` 成对下发，两处不一致。
- **状态**：已修（2026-11-21 代码审查发现并修复）。
- **修复建议**：异常路径补发 `done`，保持「任何流都以 done 收尾」的契约。
- **修复（2026-11-21）**：`agent/main.py` `_stream` 的 `agent_task.result()` 异常分支在 `yield error` 后补 `yield done({"finish_reason":"error"})`，与同文件静默失败路径（error+done 成对）对齐。至此 Agent 三条收尾路径（正常 / 静默失败 / 异常）均以 `done` 结束。

## BUG-042 · _parse_date_range 跨年日期区间解析错误

- **现象**：「复盘 12月30日 到 1月2日」被解析成同年 1月2日~12月30日（跨整年），报告窗口完全错误。
- **层面**：Agent（日期解析）。
- **根因**：`agent/agent.py:127-141` 的 `_parse_date_range` 一律用 `date.today().year`，且 `end < start` 时直接交换（把「12-30 → 次年 1-2」当成「1-2 → 12-30」）。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：当 `end` 月 < `start` 月时视为次年；跨年区间不要简单交换。

## BUG-043 · 发送与会话历史懒加载竞态，流式消息整组丢失

- **现象**：切到某个会话（触发历史懒加载）后立刻输入并发送 → 历史返回时整组覆盖 `session.messages`，刚 push 的用户消息连同正在流式渲染的 AI 消息一起脱离渲染树；且 `_hydrated` 已置 true 不再重拉，消息**永久丢失**，需整页刷新才能恢复。
- **层面**：前端（chat store）。
- **根因**：`frontend/src/stores/chat.js:125-137` 的 `hydrateSession` 异步返回后 `session.messages = items.map(toMessage)` **整数组覆盖**；`send` 既不 `await` 也完全不感知 `session._loading`。
- **状态**：已修（2026-11-21 代码审查发现并修复）。
- **修复建议**：`send` 前 `await hydrateSession`；或在 `hydrateSession` 覆盖时保留本地尚未落库的消息（按临时 id 过滤）。
- **修复（2026-11-21）**：`hydrateSession` 改为「已在加载时返回在途 Promise」——`session._hydratePromise` 记录在途加载，`_loading=true` 时直接 `return session._hydratePromise`，保证调用方能等到同一趟加载而非立即返回；`send` 在 push 本轮 user/ai 消息前先 `if (conversationId != null && !_hydrated) await hydrateSession(session)`，历史先就位、再追加本轮消息，杜绝整组覆盖。三个场景走查：切会话立刻发（等待在途加载）、已加载会话（跳过）、新草稿 conversationId=null（跳过）均正确。

## BUG-044 · done 事件无条件覆写 error 状态

- **现象**：任何业务错误（2002/2006/3001…）后消息最终 `status='done'`；若错误发生前已收到 `status` 思考步骤，`ChatMessage.vue` 的思考折叠记录（要求 `status==='done'`）会把「已生成方案…」显示在错误气泡旁，看起来像成功。
- **层面**：前端（SSE 状态机）。
- **根因**：后端 `chat.py:378-385` 在 `finally` 中总在 error 事件之后补发 `done`；`frontend/src/stores/chat.js:343-349` 的 done 分支无条件 `aiMsg.status='done'`，把刚设置的 `status='error'` 覆盖。
- **状态**：已修（2026-11-21 代码审查发现并修复）。
- **修复建议**：done 分支尊重已有 error 态（仅当非 error 时才置 done）。
- **修复（2026-11-21）**：`frontend/src/stores/chat.js` done 分支改为 `if (aiMsg.status !== 'error') aiMsg.status = 'done'`，加注释说明「done 是流结束信号、不是成功信号」。**与 BUG-041 互补不冲突**：后端/Agent 永远发 done（流必须收尾），前端收到 done 时保留 error 态（错误不被伪装成成功）。

## BUG-045 · 结构化块 __key 从未赋值，就地替换组件实例复用串脏

- **现象**：「换一换/选用候选/确认方案」就地替换餐卡后，`MealCardBlock` 的选中候选高亮、展开天数、`swapping/confirming` 等局部 `ref` 全部残留：新卡候选集变了但选中 id 指向旧 candidate_id → 无候选高亮；天数变少时旧展开下标失效。
- **层面**：前端（渲染 key）。
- **根因**：`frontend/src/components/chat/ChatMessage.vue:29` 使用 `:key="block.__key"`，但全仓库 grep 确认 `__key` **从未被赋值**（仅此一处引用）→ `v-for` 退化为按下标 patch；`chat.js` 的 `replaceMealCardInPlace` 用 `splice` 在原下标就地替换新块对象，Vue 复用同一组件实例，setup 内 `ref`（非 props）不重建。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：给每个结构化块生成稳定唯一 `__key`（如 `type + raw_id + 版本`），替换时换 key 强制重建组件。

## BUG-046 · 「当前规划」面板确认方案未处理 2005 冲突

- **现象**：用户已有固定方案，再从右侧「当前规划」面板点「确认方案」→ 只弹一句「已有覆盖同期的已固定方案…」，没有「替换/取消」的继续路径。
- **层面**：前端（面板交互）。
- **根因**：`frontend/src/components/tools/panels/CurrentPlanPanel.vue:235-246` 的 `confirmPlan` 遇到 2005 只 `ElMessage(e.message)`；而 `MealCardBlock.vue:264-281` 的 `onConfirm` 捕获 2005 后会退回对话路径 `chat.send(...)` 让 Agent 走「替换/取消」追问，两处降级不一致。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：`confirmPlan` 复用 MealCardBlock 的 2005 降级（退回对话发起「替换/取消」）。

## BUG-047 · 食材清单勾选状态跨方案串数据

- **现象**：在方案 A 里勾掉「番茄@2026-11-20」，随后（面板仍挂载时）切到方案 B，B 同一天也有番茄 → 该条目进来就是已勾选，「已买 N 项」统计错误。
- **层面**：前端（清单面板）。
- **根因**：`frontend/src/components/tools/panels/GroceryPanel.vue:99` 的 `checkedMap` 以 `ingredient_id@day_date` 为键，`load()` 换方案时只替换 `groups`、不清空 `checkedMap`。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：`load()` 时重置 `checkedMap`，或按方案 id 隔离勾选态。

## BUG-048 · 档案编辑态可能回显默认值（load 未 await）

- **现象**：应用刚启动（`profile.load()` 未完成）就打开「个人档案」并点「编辑档案」→ 表单显示默认的 26 岁/158cm/58kg 等，而非用户真实档案；此时直接保存会把默认值写回。
- **层面**：前端（档案弹窗）。
- **根因**：`frontend/src/components/profile/ProfileModal.vue:351-355` 的 `onOpen` 里 `if (!profile.profile) profile.load()` **未 await**，随后 `fillForm`（`:313-338`）读 `profile.profile || {}` 用空对象填充全默认值；档案加载完成后也无 watcher 重新回填。
- **状态**：未修（2026-11-21 代码审查发现）。
- **修复建议**：`await profile.load()` 后再 `fillForm`，或加 watcher 在档案就绪后重填表单。

## BUG-049 · 应用库账号缺 DELETE 权限，整餐重生成/替换单菜/删会话运行时失败

- **现象**：真实库跑 `backend/tests/check_v21_local_edits_db.py`，走到 `POST /slot/regenerate`（整餐重生成）在 `db.flush()` 时抛 `psycopg.errors.InsufficientPrivilege: permission denied for table meal_candidate_dish`，SQL 为 `DELETE FROM app.meal_candidate_dish WHERE candidate_id=… AND dish_id IN (…)`，接口吞异常后返回「餐位修改失败，原方案保留」。同理 `dish/replace`（替换单菜）与删除会话也会命中。
- **层面**：数据库权限 + 后端写路径。
- **根因**：[03_应用账号与权限.sql](github仓库/database/03_应用账号与权限.sql#L18) 给 `app` schema 只授 `SELECT, INSERT, UPDATE`（第 18 行，`ALTER DEFAULT PRIVILEGES` 第 27 行同），**漏了 `DELETE`**；但业务代码需要硬删——[mealplan.py:593](github仓库/backend/app/routers/mealplan.py#L593) 的 `row.dishes.clear()` 配 [meal_plan.py:193](github仓库/backend/app/models/meal_plan.py#L193) 的 `cascade="all, delete-orphan"` 会对 `meal_candidate_dish` 发 DELETE；[conversations.py:181-182](github仓库/backend/app/routers/conversations.py#L181-L182) 删会话也显式 `DELETE FROM app.message / app.conversation`。库里已为 `meal_candidate_dish` 建 `trg_guard_fixed_plan_candidate_dish`（BEFORE DELETE 保护固定方案子行），说明「允许 DELETE、但受触发器保护」才是设计意图——是授权 SQL 漏了 DELETE，而非代码不该删。
- **为何「换一换」按钮不受影响**：前端卡片上的「换一换」按钮走的是 `candidate/swap`（[mealplan.py:854](github仓库/backend/app/routers/mealplan.py#L854) 的 `swap_candidate`），它只 `UPDATE slot.selected_candidate_id` + `INSERT plan_adjustment`，**全程无 DELETE**，故能正常切换已有备选候选。受影响的是需要「清空旧菜行再插新菜行」的 `regenerate_slot`（整餐重生成）与 `replace_dish`（替换单菜）两条路径。
- **状态**：已修·待部署（2026-11-21：授权 SQL 已补 `DELETE`，运行库已手动 GRANT，`regenerate_slot` 不再报权限错误；SQL 文件改动待提交/部署）。
- **修复**：`03_应用账号与权限.sql` 第 18 行与 `ALTER DEFAULT PRIVILEGES` 第 27 行补 `DELETE`，并对运行中的库 `docker exec` 执行 `GRANT DELETE ON ALL TABLES IN SCHEMA app TO diet_app;` + `ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT DELETE ON TABLES TO diet_app;`（无需重启，见「数据库灌库坑」）。根因细节：`backend/scripts/grant_diet_app.sql` 本就含 `DELETE`，仅 docker 初始化用的 `03` 漏了，两份授权脚本不一致。
- **验证**：`diet_backend` 对 `app.meal_candidate_dish / app.message / app.conversation` 的 DELETE 实测通过（`has_table_privilege`=t，且 `DELETE … WHERE false` 无权限报错）；`check_v21_local_edits_db.py` 已越过原权限错误，`regenerate_slot` 成功换出不同菜品（签名变化、其余餐位不变、2~3 候选均通过）。该脚本另有两处旧断言（第 42/43 行，期望旧候选被删除归档）与当前「复用候选行、原地更新」设计不符，属待更新的旧测试，与本 bug 无关。
