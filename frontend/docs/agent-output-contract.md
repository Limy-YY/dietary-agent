# Agent 输出契约（前端对接版 · v1 草案）

> 状态：**v1 草案**。字段以原型与 `mock/` 的产出为准，待与 Agent 同学对齐后升版。
> 前端实现位置：`src/api/agent.js`（SSE）、`src/utils/schema.js`（归一化）、`src/components/renderer/RendererHost.vue`（注册表）。

## 1. 传输：一个 SSE + 一组 REST

| 场景 | 方式 |
| --- | --- |
| 用户发消息、卡片按钮触发的动作 | `POST /api/agent/chat`，`text/event-stream` |
| 档案、当前方案、历史方案、食材清单、膳食报告 | 普通 REST，统一 `{code, message, data}` |

卡片按钮**不调 REST**，一律发固定话术进入对话流（见 §6），由 Agent 决定写库，前端随后回读 REST 拿服务端真状态。

### 1.1 请求

```http
POST /api/agent/chat
Authorization: Bearer <token>
Content-Type: application/json

{ "conversation_id": "conv_xxx 或 null", "message": "今天吃什么" }
```

### 1.2 事件

| event | 时机 | data |
| --- | --- | --- |
| `message` | 正文流式增量，多次 | `{ "delta": "已按你的" }` |
| `message` | 正文结束后**一次**下发结构化边车 | `{ "meta": { "blocks": [...] }, "conversation_id": "conv_xxx" }` |
| `done` | 流结束 | `{ "conversation_id", "message_id", "finish_reason": "stop", "suggestions": ["看完整食谱"] }` |
| `error` | 生成中失败 | `{ "code": 2003, "message": "生成失败，请重试" }` |
| `ping` | 心跳 | `{}`，前端忽略 |

约束：

- 正文只能靠 `delta` 累加，前端不做任何拼接假设；`meta` 一定在正文之后、`done` 之前。
- `meta.blocks` 允许为空数组；为空时前端只渲染正文。
- `done.suggestions` 仅作为话术提示返回；底部固定 5 个快捷与 main.html 原型一致（生成一日三餐 / 生成一周食谱 / 推荐一餐搭配 / 生成周膳食报告 / 生成月膳食报告），不把 suggestions 叠加进快捷区。
- 响应头必须是 `text/event-stream`；否则前端按 JSON 错误处理（`src/api/agent.js` 有校验）。
- 断开由前端 `AbortController` 发起，服务端应停止生成。

### 1.3 统一响应与错误码

```json
{ "code": 0, "message": "success", "data": {} }
```

| code | 含义 | 前端行为 |
| --- | --- | --- |
| 0 | 成功 | 取 `data` |
| 1002 | 登录态失效 | 清 token、派发 `sz:unauthorized`、提示重新登录 |
| 1004 | 空态（没有数据） | resolve 成 `null`，组件渲染空态，不弹错误 |
| 2002 | 参数不合法 | 提示 `message` |
| 2003 | 生成失败 | 提示 + 可重试（对话消息显示「重试」） |
| 其他 | — | 提示 `message`，抛 `ApiError` |

## 2. REST 清单

| 方法 | 路径 | 参数 | data |
| --- | --- | --- | --- |
| GET | `/api/profile` | — | `{ profile }` |
| PUT | `/api/profile` | 档案字段（见 §2.1） | `{ profile }`（重新计算 `extras.target_energy_kcal`） |
| GET | `/api/meal-plan/current` | — | `{ plan }`；无方案 → 1004 |
| GET | `/api/meal-plan/list` | — | `{ plans: [planSummary] }` |
| GET | `/api/meal-plan/:id` | — | `{ plan }`；不存在 → 1004 |
| GET | `/api/shopping-list` | `meal_plan_id`（可选，缺省为当前方案） | `{ shopping_list }`；方案未确认 → 1004 |
| GET | `/api/nutrition/report` | `meal_plan_id`（可选）；`scope=week\|month`（**扩展，待后端确认**） | `{ report }`；无可复盘方案 → 1004 |

`planSummary`：`{ plan_id, title, plan_type, range_text, status, executed, kcal, created_at }`。

### 2.1 档案字段（PUT 可只传变化的字段）

```json
{
  "sex": "女",
  "age": 26,
  "height_cm": 158,
  "weight_kg": 58,
  "activity_level": "light",
  "goal": "减脂",
  "allergies": ["花生"],
  "taboos": [],
  "extras": { "name": "小膳", "avatar": "🍃", "goals": ["减脂"], "cookware": ["灶具", "电饭煲"] }
}
```

## 3. Block 通用约定

- 每个 block 必须有 `type`；建议带一个稳定 id（`card_id` / `plan_id` / `report_id`），前端用作 `v-for` key。
- **前端不认识 `type` 时不会白屏**：`FallbackBlock` 显示 type 名 + 原始 JSON。
- 字段允许 snake_case 或 camelCase，`schema.js` 都认；缺字段给默认值，不抛错。
- 已注册的 type：`meal_card`、`meal_plan`、`recipe_detail`、`nutrition`、`report`、`sources`、`medical_hint`、`anchor`、`shopping_list`。
- 类型别名（后端换名也能接）：`recipe_card→meal_card`、`week_plan/plan_detail→meal_plan`、`recipe→recipe_detail`、`shopping/grocery→shopping_list`、`nutrition_report→nutrition`、`meal_report→report`、`source→sources`、`health_hint→medical_hint`、`jump→anchor`。

## 4. Block schema

### 4.1 `meal_card`（餐卡：单餐 / 一日三餐 / 一周）

```json
{
  "type": "meal_card",
  "plan_id": "plan_1731..._1",
  "card_id": "card_plan_...",
  "title": "🗓️ 今日食谱",
  "subtitle": "11-13 周四 · 全天约 1680 kcal",
  "scope": "day | meal | week",
  "status": "draft | candidates | fixed",
  "goal_text": "减脂 · 目标 1850 kcal",
  "target_kcal": 1850,
  "total_kcal": 1680,
  "range_text": "11-13 周四",
  "action_scope_label": "当前方案",
  "slots": [slotView],
  "days": [{ "date": "11-13", "weekday": "周四", "is_today": true, "kcal": 1680, "slots": [slotView] }],
  "reason": { "summary": "按档案与近期微量摄入平衡排出这套方案", "points": ["三餐 30/40/30 分配…"] }
}
```

- `scope=week` 用 `days`，`slots` 留空；`scope=meal` 的 `slots` 只放这一餐，其 `candidates` 用于候选单选。
- `slotView`：

```json
{
  "slot_id": "s-0-lunch",
  "meal_type": "breakfast | lunch | dinner",
  "label": "午餐",
  "time": "12:00",
  "color": "#4a7c59",
  "kcal": 620,
  "oil_g": 6,
  "salt_g": 1.8,
  "dish_text": "糙米饭 + 香煎鸡胸肉 + 清炒西兰花",
  "dish_count": 4,
  "dishes": [{ "name": "糙米饭", "amount": "1 碗", "kcal": 210, "tip": "提前泡米" }],
  "candidates": [{ "candidate_id": "lunch-c1", "name": "方案 B · 荞麦面 + 卤鸡腿", "kcal": 640, "desc": "…", "dishes": [...] }],
  "selected_candidate_id": "lunch-c0",
  "micro": [microItem]
}
```

- `reason.points` 有值时「为什么这样搭」是**前端本地弹窗**，不发请求；没有时按钮改发 `为什么这样搭` 话术。

### 4.2 `meal_plan`（完整食谱视图）

```json
{
  "type": "meal_plan",
  "plan_id": "plan_...",
  "view": "week | day",
  "title": "接下来七天食谱",
  "subtitle": "含用量与做法",
  "days": [{ "date": "11-13", "weekday": "周四", "is_today": true, "kcal": 1680, "slots": [slotView] }]
}
```

### 4.3 `recipe_detail`（详细食谱）

```json
{
  "type": "recipe_detail",
  "title": "今日三餐 · 详细食谱",
  "subtitle": "用量按身高体重估算",
  "meals": [{
    "label": "午餐", "time": "12:00", "kcal": 620,
    "dishes": [{ "name": "香煎鸡胸肉", "amount": "120 g", "kcal": 200, "tip": "少油，两面各煎 3 分钟", "steps": ["…"] }]
  }]
}
```

### 4.4 `nutrition`（宏观四环 / 微量 7 环）

> 旧称「宏观四环」，当前实现是**一个宏量环 + 7 个微量环**（蛋白/碳水/脂肪三段 + 与 `segments` 一一对应的图例）。

```json
{
  "type": "nutrition",
  "plan_id": "plan_...",
  "scope": "day | meal | week | month",
  "macro": {
    "center_value": "1680",
    "center_label": "kcal 全天",
    "segments": [
      { "name": "蛋白质", "percent": 22, "color": "protein", "tag": "达标", "tag_level": "ok", "desc": "约 92g / 目标 95g" },
      { "name": "碳水", "percent": 53, "color": "carb", "tag": "达标", "tag_level": "ok", "desc": "约 208g / 目标 230g" },
      { "name": "脂肪", "percent": 25, "color": "fat", "tag": "合理", "tag_level": "blue", "desc": "约 46g / 目标 55g" }
    ]
  },
  "micro": {
    "title": "关键微量元素覆盖",
    "items": [{ "name": "钙", "value": "99%", "ring_percent": 99, "status": "ok", "note": "约 790 mg" }]
  },
  "insights": ["蛋白质达标，减脂期有助于维持肌肉。"],
  "coverage": { "level": "ok | warn", "text": "7 项关键微量均在参考范围内" }
```

- `color` 只接受 `protein | carb | fat`；`ring_percent` 是 0–100 的数值，`value` 是展示文本（`"99%"` 或 `"5/7"`）。
- `status` 只接受 `ok | warn | danger`。

### 4.5 `report`（膳食报告卡）

```json
{
  "type": "report",
  "report_id": "report_...",
  "scope": "week | month",
  "headline": "上周膳食报告",
  "meta": { "range_start": "11-07", "range_end": "11-13", "generated_at": "2026-11-13T08:00:00Z", "valid_days": 7, "total_meals": 20, "target_kcal": 1850 },
  "summary_text": "共覆盖 7 天、20 餐。日均 1750 kcal…",
  "macro": { "center_value": "1750", "center_label": "kcal 日均", "segments": [...] },
  "micro": { "title": "关键微量周达标率（天）", "items": [{ "name": "钙", "value": "4/7", "ring_percent": 57, "status": "warn" }] },
  "daily_trend": [{ "date": "11-07", "calories": 1720, "show_date": true, "status": "ok | over | low" }],
  "insights": ["蛋白质占比 21%，落在合理区间"],
  "expanded": false
}
```

### 4.6 `sources`（来源）

```json
{
  "type": "sources",
  "title": "参考来源",
  "items": [{ "title": "中国居民膳食指南（2022）", "publisher": "中国营养学会", "published_at": "2022-04-26", "url": "http://dg.cnsoc.org/", "snippet": "" }]
}
```

### 4.7 `medical_hint`（就医提示）

```json
{
  "type": "medical_hint",
  "level": "warn",
  "title": "这不是医学诊断",
  "text": "营养建议只作饮食参考，不能替代检查与诊断。",
  "action_label": "查看参考来源"
}
```

`action_label` 有值时点击会作为用户消息发回对话流。

### 4.8 `anchor`（跳转定位）

```json
{ "type": "anchor", "items": [{ "panel": "grocery", "label": "打开食材清单" }] }
```

`panel` 只接受 `grocery | current_plan | history | report`，未知值前端忽略。

### 4.9 `shopping_list`（食材清单卡）

```json
{
  "type": "shopping_list",
  "title": "食材清单",
  "summary": "共 32 项，分 6 组",
  "groups": [{
    "group_id": "g-0-🥬 蔬菜类",
    "day": "周四", "day_date": "11-13",
    "category": "🥬 蔬菜类",
    "items": [{ "item_id": "it-0-0-西兰花", "name": "西兰花", "amount": "150 g", "is_staple": false, "checked": false }]
  }]
}
```

## 5. 前端渲染规则

1. `blocks[]` 顺序即渲染顺序；每个 block 独立渲染，一个 block 数据异常不影响其他 block。
2. `meal_card` 的按钮：换一换禁用当 `status=fixed`；单餐候选点击即发 `选用…`，确认按钮另发 `确认当前方案`。
3. 周视图默认展开「今天」；单日/单餐点击整行打开 `RecipeModal`。
4. 报告卡默认折叠，`expanded=true` 时展开。
5. 微量环颜色：`ok→var(--brand)`、`warn→#e8942c`、`danger→#c0504d`。

## 6. 动作话术表（卡片按钮 → 用户消息）

| 按钮 | 发送文本 | 说明 |
| --- | --- | --- |
| 换一换 | `更换{早餐\|午餐\|晚餐}候选` | 服务端切到下一个候选，方案退回草稿 |
| 候选单选 | `选用{餐次}{候选名}`，如 `选用午餐方案 B · 荞麦面 + 卤鸡腿` | 服务端设为该候选 |
| 确认 | `确认当前方案` | 方案置 fixed，同步生成食材清单 |
| 固定 | `固定当前方案` | 与确认同义，保留给多轮场景 |
| 为什么这样搭 | `为什么这样搭` | 仅当 `reason.points` 为空时发送 |
| 食材清单 | `看看食材清单` | 触发 shopping_list 卡 |
| 详细食谱 | `看完整食谱` | 触发 meal_plan + nutrition + sources |
| 周报告 | `生成周膳食报告` | 触发 report 卡 |
| 月报告 | `生成月膳食报告` | 触发 month 范围 report 卡 |

## 7. 空态契约

| 位置 | 触发条件 | 展示 |
| --- | --- | --- |
| 当前规划面板 | `GET /meal-plan/current` 返回 1004 | EmptyState：「还没有生效的方案」+ 两个快捷话术 |
| 历史方案面板 | 列表为空 | EmptyState：「还没有历史方案」 |
| 食材清单面板 | 返回 1004（方案未确认） | EmptyState：「清单还是空的」+ 引导确认 |
| 膳食报告面板 | 返回 1004 | EmptyState：「还没有可复盘的方案」 |
| 卡片内 | `blocks` 为空 | 只显示正文，不显示空卡片 |
| 单餐候选为空 | `candidates=[]` | 卡内提示「这一餐暂无候选」 |

## 8. 自测清单

在 `npm run dev` 下按顺序操作（`npm run e2e` 覆盖 1–6 的接口断言）：

1. **对话生成**：发「今天吃什么」→ 正文逐字出现；正文结束后出现今日餐卡 + 营养卡 + 来源卡 + 跳转条。
2. **换候选**：点午餐行「换一换」→ 新消息出现，午餐菜品变了，方案标签仍是「待确认」。
3. **确认**：点「确认当前方案」→ 餐卡变「已生效」，附加食材清单卡与跳转条。
4. **面板同步**：右侧「当前规划」显示刚确认方案；「食材清单」有分组和条目；「历史方案」多出一条已确认。
5. **报告**：发「生成周膳食报告」→ 报告卡折叠态；展开后可见宏量环、7 微量环、每日热量柱、结论；「膳食报告」面板可复查。
6. **单餐**：发「推荐一餐搭配」→ 出现 3 个候选；点候选 → 新消息 + 「待选定」；再确认。
7. **档案**：点左下角用户菜单 → 个人档案 → 编辑档案 → 改体重保存 → 能量目标变化；保存后回查看态。
8. **空态**：刷新页面（Mock 内存态清空）→ 四个面板全部为空态，点击面板里的快捷按钮能重新拉起对话。
9. **异常**：浏览器断网后发送 → 消息气泡显示错误 + 「重试」；点重试能重新发一次。
10. **未知类型**：临时把某个 `type` 改成 `foobar` → 显示兜底 JSON，其他卡片正常。

自测结论（2026-11-13，Mock 环境）：

- 契约级 `npm run e2e`：11/11 通过（含第 1–6 条的接口断言、档案写回、2002 参数校验）。
- 真浏览器 `npm run e2e:ui`：18/18 通过（第 1–4、6–8 条的界面断言，另加首屏问候语、新对话欢迎页、底部 5 快捷、四面板空态、周视图、单餐候选、就医提示卡、对话生成报告后报告面板同步与控制台零报错），截图见 `docs/screenshots/`。
- 第 5 条报告卡与报告面板：由 UI 冒烟第 8 项覆盖（宏量环 + 7 微量环 + 结论）；每日热量柱依赖报告里的 `daily_trend`，单日方案的报告没有该字段，故只在对周/月报告时出现。
- 第 9 条断网重试、第 10 条未知类型兜底：代码路径已实现（`ChatMessage` 的 retry、`FallbackBlock`），未纳入自动脚本，留待真机人工点一次。
- 真实后端联调待接口可用后复测 SSE 心跳与 `scope` 参数。
