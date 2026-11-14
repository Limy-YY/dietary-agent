import http from './http.js'

/** GET /meal-plan/current：无方案时 data=null（不算错误） */
export async function fetchCurrentPlan() {
  return (await http.get('/meal-plan/current')) || null
}

/** GET /meal-plan/list：分页结构 {total,page,page_size,items}，page 从 1 开始 */
export async function fetchPlanList({ page = 1, pageSize = 20, status } = {}) {
  const params = { page, page_size: pageSize }
  if (status) params.status = status
  const data = await http.get('/meal-plan/list', { params })
  if (!data || typeof data !== 'object') return { total: 0, page, page_size: pageSize, items: [] }
  return {
    total: Number(data.total) || 0,
    page: Number(data.page) || page,
    page_size: Number(data.page_size) || pageSize,
    items: Array.isArray(data.items) ? data.items : []
  }
}

/** GET /meal-plan/{plan_id} */
export async function fetchPlanById(planId) {
  if (!planId) return null
  return (await http.get(`/meal-plan/${encodeURIComponent(planId)}`)) || null
}

/** POST /meal-plan/week/generate */
export async function generatePlan(payload) {
  return (await http.post('/meal-plan/week/generate', payload)) || null
}

/** POST /meal-plan/candidate/swap：fixed 方案会返回 2005 */
export async function swapCandidate({ mealPlanId, mealSlotId, candidateId, reason }) {
  const body = { meal_plan_id: mealPlanId, meal_slot_id: mealSlotId }
  if (candidateId != null) body.candidate_id = candidateId
  if (reason) body.reason = reason
  return (await http.post('/meal-plan/candidate/swap', body)) || null
}

/** POST /meal-plan/week/fix：selections 为空时按已选候选固定 */
export async function fixPlan({ mealPlanId, selections }) {
  const body = { meal_plan_id: mealPlanId }
  if (Array.isArray(selections) && selections.length) body.selections = selections
  return (await http.post('/meal-plan/week/fix', body)) || null
}
