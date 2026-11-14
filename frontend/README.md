# 膳宝 · 膳食搭配智能体前端

对话式膳食规划前端：左侧会话列表、中间对话 + 结构化卡片、右侧四个数据面板。技术栈 Vue 3 + Vite + Element Plus + Pinia + Vue Router + Axios。

- 交付范围：前端全量（对话界面 / schema 渲染器 / 四面板 / 轻量档案 / SSE 联调）
- 默认启动自带 Mock 后端（与真实后端同一份 v1.2 契约），不装后端也能完整跑通
- 所有非对话数据走 REST；拿不到就渲染空态，不编数据

## 运行

```bash
npm install
npm run dev        # http://127.0.0.1:5173
npm run build      # 产物在 dist/
npm run preview    # 预览构建产物
npm run e2e        # 契约级端到端断言（需先 npm run dev）
npm run e2e:ui     # 真浏览器 UI 冒烟（需先 npm run dev，用本机 Chrome）
```

### Mock 与真实后端切换

| 变量 | 位置 | 说明 |
| --- | --- | --- |
| `VITE_USE_MOCK` | `.env.development` / `.env.production` | `true` 走内置 Mock（开发默认），`false` 走真实后端 |
| `VITE_API_BASE` | `.env.development` | 真实后端地址，例如 `http://127.0.0.1:8000`；`VITE_USE_MOCK=false` 时由 Vite 把 `/api` 代理到该地址 |
| `VITE_DEMO_TOKEN` | `.env.development` | 演示用 JWT；Mock 只校验 `Authorization` 头是否存在，不校验签名 |

接真实后端：把 `.env.development` 改成 `VITE_USE_MOCK=false`，确认后端监听 `VITE_API_BASE`，重启 dev server 即可。生产构建默认 `VITE_USE_MOCK=false`、`VITE_API_BASE` 为空，由同源网关或反向代理提供 `/api`。

## 目录

```
mock/                     Mock 后端（Vite 中间件挂在 /api），与真实后端同一份 v1.2 契约
  data.js                 7 天菜谱、候选池、宏量/微量/报告数值
  store.js                内存态：档案、当前方案、历史方案、报告 + 结构化边车构造
  v12.js                  v1.2 payload 转换层（meal_plan_id / portion_text / micro_estimate 等）
  index.js                SSE 五类事件 + REST 路由 + 意图路由（模拟 Agent）
src/
  api/                    http.js（axios 拦截器）、agent.js（SSE）、profile/mealPlan/shopping/nutrition
  stores/                 chat（会话 + SSE 事件）、profile、panel（右侧面板）
  components/
    chat/                 对话区：ChatPane / ChatMessage / ChatComposer / WelcomeScreen
    renderer/             schema 渲染器：RendererHost + 四类 blocks + widgets + RecipeModal
    sidebar/              会话列表
    tools/                右侧四面板（食材清单 / 当前规划 / 历史方案 / 膳食报告）
    profile/              轻量档案弹窗 + 胶囊标签
    common/               EmptyState 等
  utils/schema.js         v1.2 字段适配层（null 语义、四类 artifact 归一化）
  utils/format.js         时间/热量格式化
  constants/actions.js    固定话术表 + 快捷 chips + 面板定义
  styles/                 tokens.css（设计 token）+ base.css（全站样式）
docs/
  agent-output-contract.md   Agent 输出契约 v1.2（SSE / payload / REST / 错误码 / schema 不变量）
  screenshots/               自动 UI 冒烟截图（00~15）
  ui-spec.md                 UI 规范（设计 token + 组件规范）
  ui-screens/                组件视觉稿（欢迎页 / 餐卡 / 面板 / 档案 / 空态 / toast 等）
scripts/e2e.mjs            契约级端到端断言（SSE + REST + 错误码）
scripts/ui-smoke.mjs       真浏览器 UI 冒烟（playwright-core 驱动本机 Chrome）
```

## 交付项对照

| 任务书交付项 | 落地位置 |
| --- | --- |
| ① 脚手架 + 请求层 | `package.json`、`vite.config.js`、`src/api/*`、`src/utils/schema.js` |
| ② schema 驱动的结构化渲染器 | `src/components/renderer/RendererHost.vue` + 四类 `blocks/*`，未知 type → `FallbackBlock` |
| ③ 对话界面（会话列表/气泡流/SSE/输入框+chips） | `src/components/chat/*`、`src/components/sidebar/*`、`src/stores/chat.js` |
| ④ 餐卡/周视图/单餐/详细食谱/宏量环/7 微量环/报告 | `MealCardBlock`、`CurrentPlanBlock`、`ReportBlock`、`ShoppingBlock`、`MacroDonut`、`MicroRing`、`RecipeModal`、`FallbackBlock` |
| ⑤ 右侧四面板（真实 REST + 空态） | `src/components/tools/ToolRail.vue` + `panels/*` |
| ⑥ 轻量档案 + 胶囊标签 | `src/components/profile/ProfileModal.vue`、`PillGroup.vue` |
| ⑦ 端到端联调 | `npm run e2e`（对话 → 生成 → 换候选 → 确认 → 面板同步） |

说明：v1.2 只保留 `meal_card / shopping_list / current_plan / nutrition_report` 四类 artifact。v1 草案里的来源卡、就医提示卡、锚点卡、独立食谱卡已移除；就医边界改为正文文本，卡片跳转由固定话术进入对话流，不再单独渲染结构化块。

## 团队分工与文件归属

| 成员 | 岗位 | 负责的文件 |
| --- | --- | --- |
| 王怡婷 | 前端实现与联调 | `src/api/`、`src/stores/`、`src/components/`（`src/styles/` 除外）、`src/utils/`、`src/constants/`、`mock/`、`scripts/`、`docs/agent-output-contract.md`、`docs/screenshots/`、根配置 |
| 陈婉凤 | UI 规范与视觉 | `docs/ui-spec.md`、`docs/ui-screens/`、`src/styles/tokens.css`、`src/styles/base.css` |

`src/styles/` 是陈婉凤的视觉实现，前端组件只按 token 接入，不在业务组件里重复写死颜色与字号。UI 规范与视觉稿以 `docs/ui-spec.md`、`docs/ui-screens/` 为准；联调截图以 `docs/screenshots/` 为准。

## 契约要点

### SSE 事件

| 事件 | data 结构 | 前端处理 |
| --- | --- | --- |
| `message` | `{type:'text', content}` | 追加正文增量 |
| `artifact` | `{type, payload}` | 按四类 type 归一化后入渲染队列 |
| `clarify` | `{question, missing_fields[]}` | 展示追问，补全缺失字段 |
| `error` | `{code, message}` | 标记失败，错误码语义同 REST |
| `done` | `{conversation_id, meal_plan_id, finish_reason}` | 保存会话/方案 id，通知面板刷新 |

### 数值规则

- `null` / 缺字段 = 未知，视图显示「—」或「暂无数据」，**绝不回落成 0**。
- `0` 是有效数值，正常显示为 0。
- 前端不重算 BMR、宏量、微量、油盐；只展示契约给出的数值。

### 错误码

| 码 | 含义 |
| --- | --- |
| `1001` | 参数校验不通过 |
| `1002` | 未授权 / 登录失效 |
| `1003` | 无操作权限 |
| `1004` | 资源不存在（面板渲染空态） |
| `2001` | 确定性计算失败（BMR/宏量/微量/油盐） |
| `2002` | 智能体调用失败（LLM 失败或超时） |
| `2003` | 结构化输出校验失败 |
| `2004` | 数据源不可用 |
| `2005` | 方案状态不允许该操作 |
| `2006` | 当前条件排不出可行方案 |
| `3001` | 内容安全拦截 |

`2001 / 2002 / 2003 / 2004` 标记为可重试；`1002` 会清除本地 token 并广播登录失效。

## 关键设计

- **对话只走 SSE，其余全走 REST。** 卡片按钮不发 HTTP，而是发固定话术（如「更换午餐候选」「确认当前方案」）进入对话流，由 Agent 决定落库，前端再回读 REST 拿服务端真状态。
- **渲染完全由前端注册表驱动。** Agent 只下发 `type` 与 `payload`，长什么样由 `RendererHost` 的 `REGISTRY` 决定；遇到没见过的 `type` 用 `FallbackBlock` 原样展示，绝不白屏。
- **`schema.js` 是唯一适配层。** 四类 artifact 统一在这里归一化，组件不再二次归一化；`nutrition_report` 归一化后仍保留契约原名，不改叫 `report`。
- **报告完整度读契约字段。** 面板用 `completeness.known_meal_count / meal_count`，不拿 `meta.valid_days` 充当已知餐数。
- **空态优先。** `code=1004` 在 axios 拦截器里 resolve 成 `null`，面板和卡片据此渲染空态，不伪造数据。

## 自测记录

两套脚本，都在 `npm run dev` 起服务后跑；均已通过。

**契约级（`npm run e2e`，15/15）**：健康检查、Mock 状态重置、无 token → 1002、档案读取（v1.2 字段）、今日三餐 `meal_card`、换候选后 `selected_candidate_id` 变化、确认 → `fixed` + `shopping_list`、REST 回读 current/shopping/report/list、生成周膳食报告 `nutrition_report`、单餐 3 候选、周方案生成支持 `meal_types + candidates_per_slot`、`PUT /api/profile` 重算目标能量、空 message → 1001、fixed 方案换候选 → 2005、非法 `goal_code` → 1001。

**真浏览器 UI（`npm run e2e:ui`，19/19）**：

| 断言 | 结果 |
| --- | --- |
| 首屏渲染（问候语 + 三栏） | 通过（「你好，我是膳宝。」与 main.html 一致） |
| 开启新对话后展示欢迎页 | 通过（logo + 今天想吃点什么） |
| 底部固定 5 个快捷（对齐 main.html） | 通过（生成一日三餐 / 一周食谱 / 推荐一餐 / 周报 / 月报） |
| 四个面板初始均为空态 | 通过（1004 → EmptyState，不编数据） |
| 底部 chip → SSE 流式 → 今日餐卡 3 行餐次 | 通过 |
| 换候选 → 午餐菜品变化 | 通过 |
| 单餐点击 → 详细食谱弹窗 | 通过 |
| 确认当前方案 → 餐卡「已生效」 | 通过 |
| 右侧「当前规划」显示服务端状态 | 通过（已生效 + 方案概览） |
| 「食材清单」有真实分组条目与估算量 | 通过（面板作用域内断言，条目含数字估算量） |
| 「膳食报告」宏量环 + 7 微量环 + 数据质量 | 通过（方案级报告，含完整度与结论） |
| 「历史方案」列表 | 通过 |
| 周视图（7 天折叠卡，首日展开） | 通过 |
| 单餐视图（多候选卡） | 通过（方案 A/B/C 候选） |
| 症状咨询给出就医边界 | 通过（v1.2 无 `medical_hint` artifact，边界写在正文） |
| 对话内报告卡带日期区间与餐数 | 通过 |
| 对话生成报告 → 报告面板同步 | 通过（面板回看同一份方案报告，完整度与餐数一致） |
| 轻量档案弹窗（查看态） | 通过 |
| 控制台无 JS 报错 | 通过 |

以上断言可复跑：先 `npm run dev`，再 `npm run e2e` / `npm run e2e:ui`（运行结果直接在终端输出）。自动截图在 `docs/screenshots/`；`docs/ui-screens/` 是陈婉凤的组件视觉稿，不是自动冒烟截图。

> `playwright-core` 只作 devDependency 给冒烟脚本用，直接 `executablePath` 指向本机 Chrome / Edge，不额外下载 Chromium，不进构建产物。

## 已知限制

- 前端只实现 v1.2 契约；真实后端需按《后端接口契约 v1.2》提供 SSE 与 REST，否则需调整适配层。
- 报告只支持方案级：`GET /api/nutrition/report?meal_plan_id=...`，`report_type` 固定 `plan`；不支持 `scope=week|month` 的跨方案汇总。
- 轻量档案不含账号体系；Mock 用固定演示 token，真实环境由登录流程写入 `localStorage.sz_token`。
- 浏览器端勾选食材不落库，仅本次会话内有效。
- 构建已通过，但 Element Plus 全量引入会产生 chunk 体积告警，尚未做按需引入优化。
