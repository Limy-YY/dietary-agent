# 前端 Agent 输出契约（v1.2 对齐版）

> 本文件是前端侧**唯一字段源**。字段名、枚举、`null` 语义一律以团队《Agent 输出契约 v1.2-r2》与《后端接口契约 v1.2》为准；本文件只记录前端如何消费，不再维护第二套字段。
>
> 版本：v1.2（2026-11-14 改造）
> 对应代码：`src/utils/schema.js`（唯一适配层）、`src/api/*`、`src/stores/chat.js`、`mock/*`

---

## 1. 总则

### 1.1 SSE 事件

`POST /api/agent/chat`，`Content-Type: text/event-stream`。请求体：

```json
{ "conversation_id": "conv_xxx | null", "message": "生成一周食谱", "context": { "meal_plan_id": 101 } }
```

事件类型固定四类 + 结束事件：

| event | data | 前端处理 |
|---|---|---|
| `message` | `{"type":"text","content":"…"}` | `type === 'text'` 时把 `content` 追加到当前 AI 气泡；空内容不建气泡 |
| `artifact` | `{"type":"meal_card\|shopping_list\|current_plan\|nutrition_report","payload":{…}}` | 立即归一化并渲染/更新；同 `type + raw_id` 原位替换，不重复追加 |
| `clarify` | `{"question":"…","missing_fields":["gender","age"]}` | 在气泡内渲染追问与缺失字段，不新增 assistant 轮次 |
| `error` | `{"code":2001,"message":"…"}` | 气泡内提示错误码语义；`2001~2004` 可重试，其余不自动重试 |
| `done` | `{"conversation_id":"…","meal_plan_id":101,"finish_reason":"stop"}` | 记录会话与方案 id，刷新右侧面板，结束当前流 |

约束：

- 一次对话可下发多个 `artifact`；`done` 必发且只发一次。
- 前端**只认这四个 artifact type**；未知 type 进入 `{type:'unknown', raw_type, payload}` 兜底，按纯文本/原始 JSON 提示，不白屏。
- 流式文本按服务端切片到达，前端自行拼接，不做二次切分。

### 1.2 数值三条硬规则

| 规则 | 前端落地 |
|---|---|
| 数值只读 | 不重算热量、蛋白、油盐、微量；`macro_estimate` / `macro_summary` 原样展示 |
| `null` 语义 | `null` / 缺字段 / 空串 → 显示「—」或「数据不足」，**绝不回落 0**，不标「已达标」 |
| 溯源可查 | 候选 `sources`、报告 `sources`、`summary.reference_hints` / `data_quality_notes` 必须可见（报告底部常驻，不折叠） |

### 1.3 7 个关键微量键（固定顺序）

`calcium → iron → zinc → vitamin_a → vitamin_b1 → vitamin_b2 → vitamin_c`

- 中文名只读 `name_zh`，单位只读 `unit`，目标只读 `target`；前端不维护「键 → 中文名」映射表。
- 前端 `MICRO_KEYS` 仅用于按契约顺序遍历 `key_micro_summary`，不用于翻译。
- `status`：`达标 → ok`、`不足 → warn`、`参考提示 → neutral`；`neutral` 用中性色 +「提示」标签，不用红色错误态。
- `intake === null` → 数值显示「—」，说明文案「数据不足」。

---

## 2. MealCard（`type: "meal_card"`）

### 2.1 字段（前端读取）

| 字段 | 类型 | 前端用途 |
|---|---|---|
| `meal_plan_id` | integer | 方案 id；`raw_id`，同 id 的卡原位替换 |
| `plan_type` | `餐\|日\|多日\|周\|自定义` | 标题：一餐搭配 / 今日三餐 / 多日方案 / 一周食谱 / 膳食方案 |
| `status` | `draft\|candidates\|fixed` | `candidates` 显示「待确认」+ 换候选/确认入口；`fixed` 只读、隐藏换候选 |
| `start_date` / `end_date` | `YYYY-MM-DD` | 卡头日期范围 |
| `goal_code` | enum / null | 仅透传，展示不自行翻译 |
| `goal_energy_kcal` | number / null | 「目标 N kcal」，null 显示「—」 |
| `macro_ratio` | object / null | 早/午/晚占比，仅展示，不参与计算 |
| `slots[]` | array | 餐位；按 `slot_date` + `display_order` 排序 |
| `slots[].meal_slot_id` | integer | 换候选、固定时的餐位标识 |
| `slots[].slot_date` | string | 分组日期 |
| `slots[].meal_type` | `早\|午\|晚` | 餐次文案（早餐/午餐/晚餐，时间 07:30 / 12:00 / 18:30 为前端展示常量） |
| `slots[].display_order` | integer | 同日展示顺序 |
| `slots[].target_macro` | object / null | 目标热量/蛋白；缺省时热量显示「—」 |
| `slots[].selected_candidate_id` | integer / null | 当前选中候选 |
| `slots[].candidates[].candidate_id` | integer | 候选 id |
| `slots[].candidates[].rank` | 1~3 | 候选排序 |
| `slots[].candidates[].why_text` | string | 逐候选展示「为什么这样搭」，不合并 |
| `slots[].candidates[].reason_codes` | string[] | 结构判定码，仅透传 |
| `slots[].candidates[].macro_estimate` | `{kcal, protein_g, fat_g, carb_g, fiber_g}` | 热量与宏量；`fiber_g` 归宏量，不进微量达标 |
| `slots[].candidates[].micro_estimate` | 7 键数值 / null | 该候选对微量的贡献量，非百分比 |
| `slots[].candidates[].oil_salt_estimate` | `{oil_g, salt_g}` / null | 油盐单独口径，不与宏量混排 |
| `slots[].candidates[].eating_order_advice` | string / null | 进食顺序，轻提示样式单独一行 |
| `slots[].candidates[].sources` | object[] | 溯源 |
| `slots[].candidates[].dishes[]` | array | 菜品 |
| `dishes[].dish_id` | **string**（`DISH-001`） | 菜品编码，禁止按数字处理 |
| `dishes[].name` | string | 菜名 |
| `dishes[].role` | `主食\|菜` | 角色 |
| `dishes[].servings` | number | 份数 |
| `dishes[].estimated_g` | number / null | 估算克数 |
| `dishes[].portion_text` | string / null | 份量描述（如「1 碗（熟重 150g）」）；null 显示「—」 |
| `dishes[].method_override` | string / null | 做法覆盖 |
| `dishes[].display_order` | integer | 菜内顺序 |
| `why_summary` | string | 整份方案说明 |
| `reference_hints` | string[] | 提示条，中性色 |
| `data_quality_notes` | string[] | 数据说明 |

### 2.2 渲染规则

- `plan_type=餐`：只渲染 1 个餐位，2~3 个候选竖排，点选候选发「选用第 N 个候选」；`日`：3 餐竖排；`多日/周/自定义`：按 `slot_date` 折叠成天，默认展开今天/首日。
- 每餐位热量只取选中候选 `macro_estimate.kcal`；该值为 null 时显示「— kcal」，不得用 `target_macro` 冒充实际值。
- 换候选按钮 → 发送「换一换 + 餐次」；`status=fixed` 时禁用。
- 确认按钮 → 发送「确认当前方案」；成功后卡变 `fixed`，右侧「当前规划」「食材清单」同步刷新。
- `why_text`、`oil_salt_estimate`、`eating_order_advice` 各自独立展示，不折叠进「为什么这样搭」一段里。

---

## 3. ShoppingList（`type: "shopping_list"`）

| 字段 | 类型 | 用途 |
|---|---|---|
| `shopping_list_id` | integer / null | 清单 id |
| `meal_plan_id` | integer | 归属方案 |
| `total_items` | integer | 总项数（卡头） |
| `groups[].category` | `蔬菜\|肉类\|水产\|蛋奶\|豆制品\|主食谷物\|水果\|坚果\|调料\|粮油\|其他` | 分组标题；前端只做顺序展示，不自行归类 |
| `groups[].items[].ingredient_id` | string（`CN-1032`） | 勾选键 |
| `groups[].items[].name` | string | 名称 |
| `groups[].items[].estimated_quantity` | number / null | 估算数量；null → 显示「估算量待补」 |
| `groups[].items[].unit` | string / null | g / ml / 个 / 份 等 |
| `generated_at` | string / null | 生成时间 |

规则：

- **无 `is_staple`**；常备粮油只用固定文案提示，不伪造字段。
- 方案未固定时接口返回 `2005`，面板显示「方案还没固定」空态 + 确认入口，不渲染空清单。
- 底部固定说明：数量为估算量，按实际采购调整；粮油等常备品类按家中存量自行增减。

---

## 4. CurrentPlan（`type: "current_plan"`）

| 字段 | 类型 | 用途 |
|---|---|---|
| `has_plan` | boolean | false 时不画空表，显示「暂无进行中的规划」引导 |
| `meal_plan_id` | integer / null | 方案 id |
| `plan_type` | `餐\|日\|多日\|周\|自定义` / null | 标题 |
| `status` | `candidates\|fixed` / null | 「待确认 / 已生效」 |
| `start_date` / `end_date` | string / null | 日期范围 |
| `fixed_at` | string / null | 固定时间；`candidates` 时为空 |
| `goal_energy_kcal` | number / null | 「N kcal 目标」 |
| `slots[].meal_slot_id` / `slot_date` / `meal_type` / `display_order` | — | 按天分组展示 |
| `slots[].selected_candidate_id` | integer / null | 透传 |
| `slots[].dish_ids` | string[] | 菜品编码 |
| `slots[].dish_names` | string[] | 菜品名（列表主文案） |
| `slots[].kcal` | number / null | 该餐热量；null 显示「—」 |

规则：只展示生效方案摘要，不含候选；`has_plan=false` 或接口 `1004` 时为空态，不编数据。

---

## 5. NutritionReport（`type: "nutrition_report"`）

| 字段 | 类型 | 用途 |
|---|---|---|
| `nutrition_report_id` | integer / null | 报告 id |
| `report_type` | `plan\|week\|month\|custom` | 前端只渲染 `plan`；其他类型回「仅支持方案级报告」 |
| `meal_plan_id` | integer / null | 归属方案 |
| `period_start` / `period_end` | string / null | 「区间」文案 |
| `window_days` | 3~30 | 统计窗口 |
| `macro_summary.energy_kcal` | number / null | 宏量环中心值 |
| `macro_summary.protein_pct / fat_pct / carb_pct` | number / null | 三段供能比；null 显示「—」 |
| `macro_summary.oil_g / salt_g / fiber_g` | number / null | 「烹调油 / 食盐 / 膳食纤维」三项独立指标 |
| `key_micro_summary.<nutrient_id>` | 对象，固定 7 键 | 微量区；每项含 `name_zh / target / unit / intake / gap / covered_pct / status` |
| `summary.reference_hints` | string[] | 参考口径说明（如「本期铁按普通口径，未区分经期」） |
| `summary.data_quality_notes` | string[] | 数据质量说明 |
| `completeness.meal_count / known_meal_count / missing_meal_count` | integer / null | 「共 N 餐 · 已知 N 餐 · 缺失 N 餐」 |
| `sources` | object[] | 参考值来源 |
| `generated_at` | string / null | 生成时间 |

规则：

- 微量顺序固定 7 键；`status=参考提示` 中性色 +「提示」，不得红色。
- `intake=null` → 「—」+「数据不足」；不允许显示 0%。
- 钠只在 `macro_summary.salt_g`，不进微量区。
- `summary.data_quality_notes` 与 `completeness` 在面板底部常驻展示，不折叠。
- 面板请求先取 `GET /meal-plan/current`：无方案 → 配餐引导；有方案未分析 → 「生成本方案膳食报告」（`POST /nutrition/analysis`）；已生成 → 展示报告。

---

## 6. REST 接口（面板与心跳用，结构与 artifact payload 一致）

| 方法 | 路由 | 成功 `data` | 备注 |
|---|---|---|---|
| GET | `/api/health` | `{contract:"v1.2", mock:true}` | 探活 |
| GET | `/api/profile` | Profile 对象（11 字段 + `goal_name` + `target_calories`） | `target_calories` 只读，后端按 BMR×1.4 计算 |
| PUT | `/api/profile` | 同上 | 只接受 11 个可写字段；非法值 `1001` |
| GET | `/api/meal-plan/current` | CurrentPlan；无方案 `data:null` | 前端按空态处理 |
| GET | `/api/meal-plan/list?page=&page_size=&status=` | `{total,page,page_size,items[]}` | `items` 为摘要，不含 `slots` |
| GET | `/api/meal-plan/{id}` | MealCard | 历史详情 |
| POST | `/api/meal-plan/week/generate` | MealCard（`status:"candidates"`） | 入参 `start_date`、`end_date`（跨度 ≤31）、`plan_type`、`meal_types`（默认早/午/晚）、`candidates_per_slot`（2~3）、`goal_code`；非法 `1001`，无可行解 `2006` |
| POST | `/api/meal-plan/candidate/swap` | `{meal_plan_id, meal_slot_id, selected_candidate_id, candidate, macro_delta}` | 入参 `meal_plan_id`、`meal_slot_id`、`candidate_id?`（缺省同餐下一个未选）；已固定 `2005`；无可行 `2006` |
| POST | `/api/meal-plan/week/fix` | MealCard（`status:"fixed"`） | 有未选餐位 `2005` |
| GET | `/api/shopping-list?meal_plan_id=` | ShoppingList | 未固定 `2005` |
| POST | `/api/nutrition/analysis` | NutritionReport | `window_days` 3~30 |
| GET | `/api/nutrition/report?meal_plan_id=` | NutritionReport | 未生成 `1004` |

响应统一 `{ code, message, data }`；`code=0` 时 `data` 直接是对象（无 `profile` / `plan` / `shopping_list` / `report` 包裹）；列表接口才用 `{total,page,page_size,items}`。

---

## 7. 错误码与前端行为

| code | 语义 | 前端 |
|---|---|---|
| 0 | 成功 | 使用 `data` |
| 1001 | 参数校验失败 | 错误提示，停在本轮 |
| 1002 | 未登录/登录失效 | 提示 + 清 token + 广播登录失效 |
| 1003 | 无权限 / 资源不属于当前用户 | 提示，不重试 |
| 1004 | 资源不存在 / 报告未生成 | 面板空态；不弹全局错误 |
| 2001 | 确定性计算失败（BMR / 宏量 / 微量 / 油盐异常） | 可重试（提示重试） |
| 2002 | 智能体调用失败（LLM 失败或超时） | 可重试 |
| 2003 | 结构化输出校验失败（重试后降级纯文本） | 可重试，保留文本 |
| 2004 | 数据源不可用（成分库 / 知识库查询失败） | 可重试 |
| 2005 | 方案状态非法（fixed 换候选/固定、候选不匹配、清单未固定） | 提示并刷新面板 |
| 2006 | 约束不可满足（过敏/疾病/宗教下无可行候选） | 提示，禁用按钮 |
| 3001 | 内容安全拦截 | 提示调整表述，不自动重试 |

`RETRYABLE_CODES = [2001, 2002, 2003, 2004]`。

---

## 8. 前端适配层与不变量

`src/utils/schema.js` 是唯一适配入口：

- `numOrNull`：`null` / 缺字段 / 空串 → `null`，**绝不回落 0**。
- `fmtNum` / `fmtPct`：`null` → 「—」。
- `normalizeMealCard` → 视图模型 `{title, subtitle, slots, days, status_label, reason, reference_hints, data_quality_notes}`；`days` 按 `slot_date` 分组，天热量用 `sumKnown`（全空则为 null）。
- `normalizeSlot`：以 `selected_candidate_id` 命中候选，输出 `dishes / kcal / oil_g / salt_g`；未命中回退第一个候选。
- `normalizeCurrentPlan` / `normalizeGroups` / `normalizeReport`：只读契约字段，缺失即 null。
- `normalizeArtifact(type, payload)`：`meal_card / current_plan / shopping_list / nutrition_report` 各自归一化，`type` 保持契约原名；未知 type 给 `{type:'unknown', raw_type, payload}`。

不变量：

1. 组件层不再二次归一化已归一化的视图模型（否则 kcal 会被再次读成 null）。
2. 组件不自行维护「键 → 中文名 / goal_code → 中文」业务映射；`goal_name`、`name_zh` 由服务端提供。表单选项里的中文仅作为 UI 兜底文案（review 待确认项）。
3. 旧 `nutrition` / `meal_plan` / `sources` / `medical_hint` 等 v1 草案 block 已删除；渲染注册表只保留契约四类 type，其余一律 `FallbackBlock`。
4. mock 的 `POST /api/__reset` 仅用于联调重置，不属于契约。

---

## 9. 验证

| 命令 | 覆盖 |
|---|---|
| `npm run build` | 产物构建（0 error） |
| `npm run e2e` | 15 项：health / 1002 / profile / SSE 四事件 / 换候选 / 固定 / 清单 / 报告 1004+analysis / 分页 / 单餐 / 生成可选参数 / 档案重算 / 1001 / 2005 |
| `npm run e2e:ui` | 19 项：空态 → 生成 → 换候选 → 食谱弹窗 → 确认 → 四面板 → 周视图 / 单餐 / 症状边界 / 报告同步 / 档案查看；截图输出 `docs/screenshots/` |

> 与团队契约冲突时，以团队《Agent 输出契约 v1.2-r2》原文为准；本文件只描述前端消费方式，不新增字段。
