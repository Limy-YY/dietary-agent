import http from './http.js'

/**
 * 膳食报告。
 * 主用法：?meal_plan_id=xxx（当前方案复盘）
 * 扩展用法（待后端确认是否提供）：?scope=week|month，用于「近7天 / 本月」复盘
 */
export async function fetchReport({ mealPlanId, scope } = {}) {
  const params = {}
  if (mealPlanId) params.meal_plan_id = mealPlanId
  if (scope) params.scope = scope
  const data = await http.get('/nutrition/report', { params })
  return data ? data.report || null : null
}
