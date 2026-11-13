# 膳宝 · UI 规范（设计 Token + 组件规范）

> 适用项目：膳食搭配智能体（海底小纵队）｜前端：Vue3 + Vite + Element Plus
> 规范来源：原型 `main.html` 的视觉基线，落地实现为 `src/styles/tokens.css`（token）与 `src/styles/base.css`（组件样式）。
> 本文档为 UI 岗交付物第 1 项；第 2、3 项对应 `tokens.css` / `base.css` 与本文「组件规范」章节。

---

## 1. 设计原则

1. **绿色为唯一主色**，只用于「可操作 / 已生效 / 品牌标识」三处，避免整屏泛绿。
2. **信息分层靠字号与灰度，不靠色块**：正文 15px，辅助 12–13px + `--text-sub`。
3. **卡片即容器**：对话里的结构化结果统一 14px 圆角白卡 + 1px `--border-strong` 边框，不叠多层阴影。
4. **空态必须给出下一步**：图标 + 标题 + 说明 + 可点击的引导卡片，而不是一句「暂无数据」。
5. **圆角三档**：12px（气泡、区块）、14–16px（卡片、弹窗）、999px（按钮、胶囊、chip）。

---

## 2. 色彩 Token

| Token | 值 | 用途 |
| --- | --- | --- |
| `--bg-color` | `#f7f7f7` | 应用底色 |
| `--chat-bg` | `#fbfbfb` | 对话区 / 输入区底 |
| `--panel-bg` | `#ffffff` | 右侧工具面板 |
| `--sidebar-bg` | `#fbfbfb` | 左侧会话栏 |
| `--text-main` | `#1a1a1a` | 主文字 |
| `--text-sub` | `#8a8a8a` | 次要文字、说明、时间戳 |
| `--border` | `#e2e2e2` | 常规分割线 |
| `--border-strong` | `#c8c8c8` | 卡片 / 输入框 / 未选中胶囊描边 |
| `--brand` | `#4a7c59` | 主色：确认按钮、选中态、品牌标识 |
| `--brand-hover` | `#3d6a4b` | 主色 hover / 深色文字 |
| `--brand-light` | `#eef3ee` | 选中背景、用户气泡底、空态图标底 |
| `--brand-medium` | `#dce8df` | 浅描边、打字指示点 |

**图表三色 + 状态色**

| Token | 值 | 语义 |
| --- | --- | --- |
| `--chart-protein` | `#5ba36c` | 蛋白质 |
| `--chart-carb` | `#f2a33a` | 碳水 |
| `--chart-fat` | `#3b8cf2` | 脂肪 |
| `--chart-empty` | `#f0f0f0` | 环形/进度槽底 |
| `--chart-warn` | `#f2a33a` | 偏低 / 提醒 |
| `--chart-danger` | `#ef5350` | 超标 / 风险 |

**餐次识别色（周视图、食谱弹窗的左侧色条）**

| Token | 值 |
| --- | --- |
| `--meal-breakfast` | `#e8942c` 早餐 |
| `--meal-lunch` | `#4a7c59` 午餐 |
| `--meal-dinner` | `#3b7fd4` 晚餐 |

> 状态标签：`draft`（待确认）= 底 `#faf5ee` / 字 `#a07b4f`；`fixed`（已生效）= 底 `--brand-light` / 字 `--brand-hover`。禁止用红色表示「待确认」。

---

## 3. 字体与字号阶梯

字体族：`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Roboto, Arial, sans-serif`（`--el-font-family`，全站与 Element Plus 共用）。

| 字号 | 字重 | 用途 |
| --- | --- | --- |
| 17px / 1.5 | 600 | 首屏问候语 |
| 16px | 600–700 | 品牌名、面板标题 |
| 15.5px | 600 | 卡片标题、报告标题 |
| 15px / 1.65–1.8 | 400–500 | 正文、AI 气泡、菜名 |
| 14.5px | 400 | 问候副标题 |
| 14px | 600 | 空态引导卡标题 |
| 13.5px | 600 | 「开启新对话」按钮 |
| 13px / 1.6–1.7 | 400–600 | 说明文字、次按钮、chip、胶囊、报告摘要 |
| 12.5px | 400–500 | 报告元信息、字段标签 |
| 12px | 400–600 | 辅助说明、时间戳、徽标、空态描述 |
| 11–11.5px | 400 | 输入框提示、面板时间戳 |
| 10px | 500 | 面板类型标签、工具徽标数字 |

行高：正文 1.65–1.8；说明类 1.5–1.7；标题 1.3–1.5。

---

## 4. 间距、圆角、阴影、布局

**间距阶梯**：4 / 6 / 8 / 10 / 12 / 14 / 16 / 18 / 20 / 24 px。常用组合：卡片头 `18px 20px`、卡片脚 `14px 20px`、餐次行 `14px 20px`、面板体 `16px 20px 20px`。

**圆角**：`--radius: 12px`（默认）；气泡 12px；卡片 14px；输入框 16px；空态图标 16px；弹窗 16px；按钮 / chip / 胶囊 / 筛选 999px；小方块（换一换）999px、发送键 10px。

**阴影**

| 场景 | 值 |
| --- | --- |
| 卡片常态 | `0 1px 3px rgba(0,0,0,.05)` |
| 卡片 / 引导卡 hover | `0 4px 12px rgba(0,0,0,.05)` |
| 开启新对话按钮 | `0 2px 8px rgba(0,0,0,.06)`；hover `0 6px 16px rgba(74,124,89,.18)` |
| 右侧面板 | `-4px 0 16px rgba(0,0,0,.03)` |
| 弹窗 | `0 18px 50px rgba(0,0,0,.18)` |
| 输入框聚焦 | `0 0 0 3px rgba(74,124,89,.10)` |

**布局尺寸**

| Token | ≥1280px | ≤1280px |
| --- | --- | --- |
| `--left-w` 左栏 | 260px | 224px |
| `--tool-bar-w` 工具条 | 64px | 64px |
| `--tool-panel-w` 面板 | 340px | 300px |
| `--content-max-w` 对话内容宽 | 880px（≥1900px 时 980px） | 880px |

≤1080px 隐藏左侧会话栏（`display:none`），保留折叠按钮。

**动效**：常规 `0.15s / 0.2s / 0.22s ease`；布局展开 `width 0.3s cubic-bezier(.4,0,.2,1)`；流式光标 `1s steps(2) infinite`；打字三点 `1.2s` 错峰（0 / .2 / .4s）；骨架屏 `1.4s` 位移渐变。禁止超过 0.4s 的入场动画。

---

## 5. Element Plus 主题映射

组件库不单独配色，全部跟随 token：

```
--el-color-primary: #4a7c59
--el-color-primary-light-3/5/7/8/9: #77987f / #a4baa9 / #cbd9cd / #dce8df / #eef3ee
--el-color-primary-dark-2: #3d6a4b
--el-border-radius-base: 10px
--el-text-color-primary: #1a1a1a
--el-text-color-regular: #4a4a4a
--el-text-color-secondary: #8a8a8a
--el-border-color: #e2e2e2
--el-border-color-light: #ededed
--el-font-family: 见第 3 节
```

使用边界：**表单控件（档案弹窗的输入、选择、日期）用 Element Plus**；卡片、面板、空态、气泡、环形图一律用自有 class，不混用两套视觉。

---

## 6. 组件规范

### 6.1 三栏骨架
`左会话栏(260) | 主对话区(flex) | 工具条(64) + 工具面板(340，展开时)`。左栏与面板用宽度过渡展开/收起，不遮罩、不改布局层级。

- 品牌区：logo 32×32、圆角 9px、白底 + `--brand-medium` 描边；名称 16px/700，副名 12px/500 + 左侧 1px 分隔线。
- 「＋ 开启新对话」：胶囊按钮，`11px` 内边距、白底 + `--border-strong`、13.5px/600，hover 转 `--brand-light` 并上移 1px。

### 6.2 对话气泡
| 元素 | 规格 |
| --- | --- |
| 容器 | 宽度 100%，`max-width: --content-max-w`，水平居中 |
| 用户气泡 | 右对齐，`12px 18px`，圆角 12px，底 `--brand-light`，15px/1.65，最大宽 85% |
| AI 气泡 | 左对齐、无底色无边框，15px/1.8，段间距 8px |
| 问候语 | 首句 17px/600，副句 14.5px + `--text-sub` |
| 流式光标 | 2×15px 竖条，`--brand`，闪烁；等待态三个 5px 圆点 `--brand-medium` |
| 错误条 | 气泡末尾追加，不撤回已输出正文 |

### 6.3 结构化卡片（餐卡 / 报告卡通用）
- 容器：白底、1px `--border-strong`、圆角 14px、`margin-top: 8px`、轻阴影。
- 头部：`18px 20px`，标题 15.5px/600，副标题 13px + `--text-sub`（`margin-top:4px`），右侧状态标签 12px/600、`5px 10px`、圆角 8px。
- 餐次行：`14px 20px`，行间 1px `#f0f0f0`；左侧「餐次 13px 灰 + 菜名 15px/500 + 元信息 12px」；右侧热量 12px/600 `--brand-hover`；可点击行 hover `#fbfbfb`，cursor pointer。
- 底部操作：左「看完整食谱」13px 灰色文字链；右主按钮「确认当前方案」高 32px、胶囊、`--brand` 填充、13px/500，禁用转 `--text-sub`。
- 「换一换」：32px 高、宽 110px 列、胶囊、白底 + `--border-strong` + `--brand-hover` 文字，hover 转 `--brand-light`，禁用 `opacity:.45`。

### 6.4 周视图 / 单餐候选 / 详细食谱
- 周视图：7 张折叠卡，首日展开；展开项标题 15px/600 + 日期 12px 灰；餐次左色条按 `--meal-*`；折叠行 `aria-expanded` 可读。
- 单餐候选：纵向 `gap: 8px`，`16px 20px` 内边距；每候选「方案 A/B/C + 热量 + 4 道菜」，选中态描边 `--brand`。
- 详细食谱弹窗：`max-width 600px`、圆角 16px、`max-height 88vh`，按早/午/晚分块，块间 1px 分割 + 色条。

### 6.5 图表
- 宏量环形图：蛋白 `#5ba36c`、碳水 `#f2a33a`、脂肪 `#3b8cf2`，槽底 `--chart-empty`；中心数值 + 单位，环下 legend 带色点 + 名称 + 百分比。
- 7 关键微量环：统一 44–56px 环径、槽底 `--chart-empty`、达标 `--chart-protein`、偏低 `--chart-warn`、超标 `--chart-danger`；环下「数值 + 名称」两行 12px。
- 报告趋势：7 根柱、柱宽自适应、日期 11px 灰；数值只在 hover 或柱顶显示，避免拥挤。

### 6.6 报告卡
头部 `16px 20px`，标题 15.5px/600，元信息 12.5px 灰，摘要块 13px/1.6 + `#f7faf8` 底 + 左侧 2px `--brand` 条 + 圆角 8px；右上「展开查看」13px 胶囊，展开后转 `--brand` 填充白字；展开体 `0 20px 20px` + 上方 1px 虚线。

### 6.7 输入区与快捷 chip
- 输入区 `16px 24px 24px`；chip 行距底部 12px。
- chip：`6px 14px`、圆角 99px、白底 + `--border` + 13px 灰；hover `--brand-light` + 上移 1px；禁用 `opacity .6`；报告类 chip 用 `--brand-medium` 描边 + `#f7faf8` 底。
- 输入框：圆角 16px、`12px 16px`、白底 + `--border-strong`、轻阴影；聚焦描边 `--brand` + 3px 光晕；textarea 15px、最高 120px；占位色 `#a0a0a0`。
- 发送键 32×32、圆角 10px、`--brand`，hover 加深 + 上移 1px，禁用 `#cfd8d1`。
- 提示行 11.5px 灰、居中、距上 8px。

### 6.8 工具条与面板
- 工具项 56×82、圆角 10px、图标 20px + 文案 11px/500（两行内）、项间距 8px；hover `#f7f9f8`；激活态 `--brand` + `--brand-light` 底 + 底部 16×2px 下划线。
- 角标：最小 16px、圆角 8px、`#e8942c` 底白字 10px，距右 6、距上 8。
- 面板头：高 64px、`0 20px`、16px/600、图标 18–20px `--brand`；底部 1px 分割线左右各缩 20px。
- 面板体：`16px 20px 20px`；时间戳 11px 灰；筛选 chip `5px 12px` + 12px，选中 `--brand` 填充白字。

### 6.9 空态
- 图标块 64×64、圆角 16px、`--brand-light` 底、emoji 30px；
- 标题 15px/600、下距 6px；描述 13px/1.7 `--text-sub`、下距 20px、允许换行；
- 引导卡：纵列 `gap 10px`；单卡 `14px 16px`、圆角 12px、白底 + `--border-strong`；左图标 36×36 圆角 10px `--brand-light`；标题 14px/600，说明 12px 灰；
- hint 块：上距 20px、12px/1.7、`#f7f9f8` 底、圆角 10px、`12px 14px`、左对齐，可用 `<b>` 强调话术；
- 兜底按钮 `8px 16px` 胶囊，主版 `--brand` 填充，幽灵版白底 + `--brand-medium` 描边。

### 6.10 胶囊标签（档案）
`6px 14px`、圆角 999px、13px/500；未选：白底 + `--border-strong` + `--text-sub`；已选：`--brand-light` 底 + `--brand` 描边 + `--brand-hover` 字 + 600；「＋ 自定义」虚线描边 12.5px；自定义输入 31px 高、104px 宽、聚焦描边 `--brand`。

### 6.11 弹窗
遮罩 `rgba(20,26,22,.42)`；容器 `max-width 600px`、圆角 16px、`max-height 88vh`、`0 18px 50px rgba(0,0,0,.18)`；头部标题 16px/600；档案 hero 目标值 15px/600 `--brand`；字段标签 12.5px 灰、组间距 18px、组间 1px 分割。

### 6.12 骨架屏与提示
骨架：`#f2f2f2 → #fafafa` 1.4s 循环，行高 12px、间距 10px、圆角 8px。Toast 使用 Element Plus `ElMessage`，主色跟随 `--el-color-primary`，成功/警告文案不超过 20 字。

---

## 7. 状态与交互约定

| 状态 | 视觉 |
| --- | --- |
| hover | 描边转 `--brand` 或底色转 `--brand-light`，可叠加 `translateY(-1px)` |
| disabled | 透明度 0.45–0.6 + `cursor: not-allowed`，不改布局尺寸 |
| loading | 骨架屏或三点打字，不出现空白卡片 |
| empty | 见 6.9，必须有引导动作 |
| error | 气泡末尾追加错误条，保留已输出内容 |

一致性红线：

1. 主色只用于**可点击 / 已生效 / 品牌**，不用作大面积背景。
2. 任何「待确认 / 草稿」不得使用红色或警示色。
3. 同一屏内圆角不超过三档；卡片一律 14px。
4. 中文文案用全角标点；数字与单位之间留半角空格（`620 kcal`、`89 g`）。
5. 图标与文字基线对齐，图标尺寸固定 18/20px 两档。

---

## 8. 交付对应表（UI 岗）

| 任务书交付物 | 落地文件 | 状态 |
| --- | --- | --- |
| ① UI 规范文档（token + 组件规范） | `frontend/docs/ui-spec.md`（本文） | 已补 |
| ② 样式系统（CSS 变量 / Element Plus 主题） | `frontend/src/styles/tokens.css`（token + EP 映射）、`frontend/src/styles/base.css`（组件样式） | 已落地 |
| ③ 组件视觉稿或样式（供前端接入） | 本文第 6 节逐组件规格 + 上述两份 CSS | 已落地 |

维护约定：改视觉只改 `tokens.css` 的变量与本文对应条目；组件新样式追加到 `base.css` 对应分区，并在本文第 6 节补一条规格。
