import http from './http.js'

/** 当前生效方案；无方案时后端返回 1004 → 这里得到 null */
export async function fetchCurrentPlan() {
  const data = await http.get('/meal-plan/current')
  return data ? data.plan || null : null
}

export async function fetchPlanList() {
  const data = await http.get('/meal-plan/list')
  return data && Array.isArray(data.plans) ? data.plans : []
}

export async function fetchPlanById(planId) {
  if (!planId) return null
  const data = await http.get(`/meal-plan/${encodeURIComponent(planId)}`)
  return data ? data.plan || null : null
}
