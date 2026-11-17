import http from './http.js'

/**
 * GET /nutrition/report?meal_plan_id=
 * 方案级报告回读；周/月报告走 POST /nutrition/period-analysis（由 Agent 在对话里调用，
 * 结果作为 nutrition_report artifact 流式下发，不落库、不经本面板回读）。
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

/** GET /nutrition/report/list：报告存档列表，分页结构 {total,page,page_size,items} */
export async function fetchReportList({ page = 1, pageSize = 50 } = {}) {
  const data = await http.get('/nutrition/report/list', { params: { page, page_size: pageSize } })
  if (!data || typeof data !== 'object') return { total: 0, page, page_size: pageSize, items: [] }
  return {
    total: Number(data.total) || 0,
    page: Number(data.page) || page,
    page_size: Number(data.page_size) || pageSize,
    items: Array.isArray(data.items) ? data.items : []
  }
}

/** GET /nutrition/report/{report_id}：按 id 读取报告详情 */
export async function fetchReportById(reportId) {
  if (reportId == null) return null
  return (await http.get(`/nutrition/report/${encodeURIComponent(reportId)}`)) || null
}
