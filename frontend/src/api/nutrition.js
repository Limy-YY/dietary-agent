import http from './http.js'

/**
 * GET /nutrition/report?meal_plan_id=
 * v1.2 只支持方案级报告：report_type 固定 'plan'，不再支持 scope=week|month。
 * 未分析过 → 1004（拦截器返回 null），由面板渲染空态。
 */
export async function fetchReport({ mealPlanId } = {}) {
  if (!mealPlanId) return null
  return (await http.get('/nutrition/report', { params: { meal_plan_id: mealPlanId } })) || null
}

/** POST /nutrition/analysis：触发一次方案级分析，返回报告对象 */
export async function analyzeNutrition({ mealPlanId, windowDays = 7 } = {}) {
  if (!mealPlanId) return null
  return (
    (await http.post('/nutrition/analysis', { meal_plan_id: mealPlanId, window_days: windowDays })) || null
  )
}
