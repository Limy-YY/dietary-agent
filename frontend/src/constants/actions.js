/**
 * 卡片按钮一律发固定话术走 SSE（后端按话术路由，不新增 HTTP 接口）。
 * 话术表同时是给 Agent 同学看的输出契约，改动需同步 docs/agent-output-contract.md。
 */
export const PHRASE = {
  swap: (mealLabel) => `更换${mealLabel}候选`,
  choose: (mealLabel, candidateName) => `选用${mealLabel}${candidateName}`,
  confirm: '确认当前方案',
  fix: '固定当前方案',
  reason: '为什么这样搭',
  shoppingList: '看看食材清单',
  weekReport: '生成周膳食报告',
  monthReport: '生成月膳食报告'
}

/** 底部固定快捷，与 main.html 原型保持一致的 5 个（不再叠加后端 suggestions） */
export const PRESET_CHIPS = [
  { key: 'day', text: '🥗 生成一日三餐', phrase: '生成一日三餐' },
  { key: 'week', text: '📅 生成一周食谱', phrase: '生成一周食谱' },
  { key: 'meal', text: '🍱 推荐一餐搭配', phrase: '推荐一餐搭配' },
  { key: 'report-week', text: '📊 生成周膳食报告', phrase: PHRASE.weekReport, report: true },
  { key: 'report-month', text: '📈 生成月膳食报告', phrase: PHRASE.monthReport, report: true }
]

export const MEAL_LABELS = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐'
}

/** 与 main.html 原型一致：名称、两行标签、实时/存档类型 */
export const PANELS = [
  { key: 'grocery', icon: '🛒', label: '食材清单', line1: '食材', line2: '清单', type: 'live' },
  { key: 'current_plan', icon: '📋', label: '当前规划', line1: '当前', line2: '规划', type: 'live' },
  { key: 'history', icon: '🗂️', label: '历史方案', line1: '历史', line2: '方案', type: 'archive' },
  { key: 'report', icon: '📊', label: '膳食报告', line1: '膳食', line2: '报告', type: 'archive' }
]

export const PANEL_TYPES = {
  grocery: '实时',
  current_plan: '实时',
  history: '存档',
  report: '存档'
}

export const PANEL_TITLES = {
  grocery: '食材清单',
  current_plan: '当前规划',
  history: '历史方案',
  report: '膳食报告'
}
