import http from './http.js'

/** 食材清单；方案未确认时后端返回 1004 → null */
export async function fetchShoppingList(mealPlanId) {
  const params = mealPlanId ? { meal_plan_id: mealPlanId } : {}
  const data = await http.get('/shopping-list', { params })
  return data ? data.shopping_list || null : null
}
