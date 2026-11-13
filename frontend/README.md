# 膳宝 · 膳食搭配智能体前端

对话式膳食规划前端：左侧会话列表、中间对话 + 结构化卡片、右侧四个数据面板。技术栈 Vue 3 + Vite + Element Plus + Pinia + Vue Router + Axios。

- 交付范围：前端全量（对话界面 / schema 渲染器 / 四面板 / 轻量档案 / SSE 联调）
- 默认启动自带 Mock 后端（与真实后端同一份契约），不装后端也能完整跑通
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
| `VITE_USE_MOCK` | `.env.development` / `.env.production` | `true` 走内置 Mock（默认），`false` 走真实后端 |
| `VITE_API_BASE` | `.env.development` | 真实后端地址，例如 `http://127.0.0.1:8000`；`false` 时 `/api` 由 Vite 代理过去 |
| `VITE_DEMO_TOKEN` | `.env.development` | 演示用 JWT，Mock 校验「有 Authorization 头」即放行 |

接真实后端：把 `.env.development` 改成 `VITE_USE_MOCK=false`，确认后端监听 `VITE_API_BASE`，重启 dev server 即可。前端不需要改代码。

## 目录

```
mock/                     Mock 后端（Vite 中间件挂在 /api），与真实后端同一份契约
  data.js                 7 天菜谱、候选池、微量/宏量/报告数值
  store.js                内存态：档案、当前方案、历史方案、报告 + 结构化边车构造
  index.js                SSE 流 + REST 路由 + 意图路由（模拟 Agent）
src/
  api/                    http.js（axios 拦截器）、agent.js（SSE）、profile/mealPlan/shopping/nutrition
  stores/                 chat（会话 + SSE 三事件）、profile、panel（右侧面板）
  components/
    chat/                 对话区：ChatPane / ChatMessage / ChatComposer / WelcomeScreen
    renderer/             schema 渲染器：RendererHost + blocks/* + widgets/*
    sidebar/              会话列表
    tools/                右侧四面板（食材清单 / 当前规划 / 历史方案 / 膳食报告）
    profile/              轻量档案弹窗 + 胶囊标签
    common/               EmptyState 等
  utils/schema.js         schema 归一化（缺字段给默认、未知 type 走兜底）
  utils/format.js         时间/热量格式化
  constants/actions.js    固定话术表 + 快捷 chips + 面板定义
  styles/                 tokens.css（设计 token）+ base.css（全站样式）
docs/agent-output-contract.md   Agent 输出契约（block schema + 话术表）
docs/ui-spec.md            UI 规范（设计 token + 组件规范）
docs/ui-screens/           组件视觉稿（欢迎页 / 餐卡 / 面板 / 档案 / 空态等）
scripts/e2e.mjs            契约级端到端断言（SSE + REST + 空态）
scripts/ui-smoke.mjs       真浏览器 UI 冒烟（playwright-core 驱动本机 Chrome）
```

## 交付项对照

| 任务书交付项 | 落地位置 |
| --- | --- |
| ① 脚手架 + 请求层 | `package.json`、`vite.config.js`、`src/api/*`、`src/utils/schema.js` |
| ② schema 驱动的结构化渲染器 | `src/components/renderer/RendererHost.vue` + `blocks/*`，未知 type → `FallbackBlock` |
| ③ 对话界面（会话列表/气泡流/SSE/输入框+chips） | `src/components/chat/*`、`src/components/sidebar/*`、`src/stores/chat.js` |
| ④ 餐卡/周视图/单餐/详细食谱/宏量环/7 微量环/来源与就医提示/跳转定位 | `MealCardBlock`、`MealPlanBlock`、`RecipeDetailBlock`、`NutritionBlock`、`ReportBlock`、`SourcesBlock`、`MedicalHintBlock`、`AnchorBlock`、`MacroDonut`、`MicroRing`、`RecipeModal` |
| ⑤ 右侧四面板（真实 REST + 空态） | `src/components/tools/ToolRail.vue` + `panels/*` |
| ⑥ 轻量档案 + 胶囊标签 | `src/components/profile/ProfileModal.vue`、`PillGroup.vue` |
| ⑦ 端到端联调 | `npm run e2e`（对话 → 生成 → 换候选 → 确认 → 面板同步） |

## 团队分工与文件归属

| 成员 | 岗位 | 负责的文件 |
| --- | --- | --- |
| 王怡婷 | 前端实现 | 前端全量代码与联调：`src/`（含 `src/styles/` 的样式落地）、`mock/`、`scripts/`、`docs/agent-output-contract.md`、根配置与 `README.md` |
| 陈婉凤 | UI 规范与视觉 | `docs/ui-spec.md`（设计 token + 组件规范）、`docs/ui-screens/`（组件视觉稿）；token 与视觉基线定义 |

说明：`src/styles/tokens.css`、`src/styles/base.css` 是「按 UI 规范落地」的实现文件，由王怡婷按原型 `main.html` 的既有视觉抽取整理；规范与视觉稿以陈婉凤的 `docs(ui)` 提交为准（commit `b04a2a0`）。

## 关键设计

- **对话只走 SSE，其余全走 REST。** 卡片按钮不发 HTTP，而是发固定话术（如「更换午餐候选」「确认当前方案」）进入对话流，由 Agent 决定落库，前端再回读 REST 拿服务端真状态。
- **渲染完全由前端注册表驱动。** Agent 只下发 `type` 与数据，长什么样由 `RendererHost` 的 `REGISTRY` 决定；遇到没见过的 `type` 用 `FallbackBlock` 原样展示，绝不白屏。
- **缺字段不崩。** `src/utils/schema.js` 统一补默认值，`snake_case`/`camelCase` 都能接。
- **空态优先。** `code=1004` 在 axios 拦截器里 resolve 成 `null`，面板和卡片据此渲染空态，不伪造数据。

## 自测记录

两套脚本，都在 `npm run dev` 起服务后跑；均已通过。

**契约级（`npm run e2e`，11/11）**：健康检查、无 token → 1002、档案读取、今日三餐 meal_card、换候选（午餐菜品变化）、确认 → `fixed` + 食材清单、REST 回读一致、周报告、单餐 3 候选、`PUT /api/profile` 目标能量重算、空 message → 2002。

**真浏览器 UI（`npm run e2e:ui`，18/18）**：

| 断言 | 结果 |
| --- | --- |
| 首屏渲染（问候语 + 三栏） | 通过（「你好，我是膳宝。」与 main.html 一致） |
| 开启新对话后展示欢迎页 | 通过（logo + 今天想吃点什么 + 4 个 chip） |
| 底部固定 5 个快捷（对齐 main.html） | 通过（生成一日三餐 / 一周食谱 / 推荐一餐 / 周报 / 月报） |
| 四个面板初始均为空态 | 通过（1004 → EmptyState，不编数据） |
| 底部 chip → SSE 流式 → 今日餐卡 3 行餐次 | 通过 |
| 换候选 → 午餐菜品变化 | 通过 |
| 单餐点击 → 详细食谱弹窗 | 通过（早餐 430 kcal / 4 道菜） |
| 确认当前方案 → 餐卡「已生效」 | 通过 |
| 右侧「当前规划」显示服务端状态 | 通过（已生效 · 1700 / 目标 1820 kcal） |
| 「食材清单」有真实分组条目 | 通过（12 项 / 5 组，面板作用域内断言） |
| 「膳食报告」宏量环 + 7 微量环 + 结论 | 通过（今日三餐 · 营养复盘） |
| 「历史方案」列表 | 通过 |
| 周视图（7 天折叠卡，首日展开） | 通过 |
| 单餐视图（3 个候选） | 通过（方案 A/B/C，620–680 kcal） |
| 就医提示卡 | 通过（「这不是医学诊断」+ 参考来源） |
| 对话生成报告 → 报告面板同步 | 通过（面板回看到「上周膳食报告」，不再是空态） |
| 轻量档案弹窗（查看态） | 通过 |
| 控制台无 JS 报错 | 通过 |

以上断言可复跑：先 `npm run dev`，再 `npm run e2e` / `npm run e2e:ui`（脚本不写入仓库，运行结果直接在终端输出）。界面截图见 `docs/ui-screens/`：00 面板空态、01 新对话欢迎页、02 今日方案、04 详细食谱、06 食材清单、07 膳食报告、09 档案弹窗、10 周视图、14 对话生成报告后的报告面板。

> `playwright-core` 只作 devDependency 给冒烟脚本用，直接 `executablePath` 指向本机 Chrome，不额外下载 Chromium，不进构建产物。

## 已知限制

- `GET /api/nutrition/report?scope=week|month` 是前端提出的可选扩展参数，真实后端是否提供待确认；未提供时报告面板降级为「按方案复盘」。
- 轻量档案只覆盖身高体重年龄、目标、过敏、厨具；不含账号体系（Mock 用固定演示 token）。
- 浏览器端勾选食材不落库，仅本次会话内有效。
