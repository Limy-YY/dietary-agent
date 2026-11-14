import http from './http.js'
import { ApiError } from './http.js'

/**
 * GET /shopping-list?meal_plan_id=
 * 只有 fixed 方案可取；未固定返回 2005（方案状态非法）。
 * 这里把 2005 收敛成 { error: 'unfixed' }，由面板渲染「方案未固定」空态，
 * 不再把它当作异常弹窗处理。
 */
export async function fetchShoppingList(mealPlanId) {
  if (!mealPlanId) return null
  try {
    return (await http.get('/shopping-list', { params: { meal_plan_id: mealPlanId } })) || null
  } catch (e) {
    if (e instanceof ApiError && e.code === 2005) return { error: 'unfixed' }
    throw e
  }
}
