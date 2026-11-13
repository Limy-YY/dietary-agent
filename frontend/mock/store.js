/**
 * Mock 状态机：模拟 Agent 的「意图路由 + 确定性工具落库」结果。
 * 所有接口返回统一 { code, message, data } 结构。
 */
import { buildPlan, buildShoppingList, buildReport, planSummary, dayInfo, SOURCES } from './data.js'

const DEFAULT_PROFILE = {
  profile_id: 1,
  user_id: 'demo-user',
  sex: '女',
  age: 26,
  height_cm: 158,
  weight_kg: 58,
  activity_level: 'light',
  goal: '减脂',
  allergies: ['花生'],
  taboos: [],
  conditions: { 高血压: false, 糖尿病: false, 高血脂: false, 痛风: false },
  extras: {
    name: '小膳',
    avatar: '🍃',
    cookware: ['灶具', '电饭煲'],
    religion: ['无'],
    goals: ['减脂'],
    target_energy_kcal: 1850
  },
  birth_date: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString()
}

export const state = {
  profile: JSON.parse(JSON.stringify(DEFAULT_PROFILE)),
  currentPlan: null,
  plans: [],
  reports: []
}

/* ---------- 档案 ---------- */
export function getProfile() {
  return state.profile
}

export function saveProfile(payload) {
  const next = { ...state.profile, ...payload }
  next.extras = { ...state.profile.extras, ...(payload.extras || {}) }
  next.conditions = { ...state.profile.conditions, ...(payload.conditions || {}) }
  next.allergies = Array.isArray(payload.allergies) ? payload.allergies.filter((x) => x && x !== '无') : state.profile.allergies
  next.taboos = Array.isArray(payload.taboos) ? payload.taboos.filter((x) => x && x !== '无') : state.profile.taboos
  // 能量目标：BMR × 1.4（固定活动系数），仅作份量量级参考
  const isFemale = next.sex !== '男'
  const bmr = 10 * Number(next.weight_kg) + 6.25 * Number(next.height_cm) - 5 * Number(next.age) + (isFemale ? -161 : 5)
  next.extras.target_energy_kcal = Math.round((bmr * 1.4) / 10) * 10
  next.updated_at = new Date().toISOString()
  state.profile = next
  // 档案变更后，当前草稿方案的依据同步更新（模拟 Agent 联动）
  if (state.currentPlan) {
    state.currentPlan.goal_text = `${goalText(next)} · 目标 ${next.extras.target_energy_kcal} kcal`
    state.currentPlan.goal_energy_kcal = next.extras.target_energy_kcal
  }
  return next
}

function goalText(profile) {
  const goals = profile.extras.goals && profile.extras.goals.length ? profile.extras.goals : [profile.goal]
  return goals.join('、')
}

/* ---------- 方案 ---------- */
export function getCurrentPlan() {
  return state.currentPlan
}

export function getPlanById(id) {
  if (state.currentPlan && state.currentPlan.plan_id === id) return state.currentPlan
  return state.plans.find((p) => p.plan_id === id) || null
}

export function listPlans() {
  return state.plans.map(planSummary)
}

export function createPlan(planType) {
  const plan = buildPlan(planType)
  plan.goal_text = `${goalText(state.profile)} · 目标 ${state.profile.extras.target_energy_kcal} kcal`
  plan.goal_energy_kcal = state.profile.extras.target_energy_kcal
  state.currentPlan = plan
  return plan
}

export function confirmPlan() {
  if (!state.currentPlan) return null
  const plan = state.currentPlan
  plan.status = 'fixed'
  plan.executed = false
  plan.updated_at = new Date().toISOString()
  const exists = state.plans.findIndex((p) => p.plan_id === plan.plan_id)
  const copy = JSON.parse(JSON.stringify(plan))
  if (exists >= 0) state.plans[exists] = copy
  else state.plans.unshift(copy)
  return plan
}

export function swapCandidate(mealLabel) {
  if (!state.currentPlan) return null
  const slot = findSlot(mealLabel)
  if (!slot) return null
  const cans = slot.candidates || []
  if (!cans.length) return null
  const curIdx = cans.findIndex((c) => c.candidate_id === slot.selected_candidate_id)
  const next = cans[(curIdx + 1) % cans.length]
  slot.selected_candidate_id = next.candidate_id
  slot.dishes = JSON.parse(JSON.stringify(next.dishes))
  slot.kcal = next.kcal
  slot.macro = {
    protein_g: Math.round((next.kcal * 0.22) / 4),
    carb_g: Math.round((next.kcal * 0.5) / 4),
    fat_g: Math.round((next.kcal * 0.28) / 9)
  }
  recalcPlanKcal()
  state.currentPlan.status = 'draft'
  state.currentPlan.updated_at = new Date().toISOString()
  return { slot, candidate: next }
}

export function chooseCandidate(mealLabel, candidateName) {
  if (!state.currentPlan) return null
  const slot = findSlot(mealLabel)
  if (!slot) return null
  const cans = slot.candidates || []
  const target = cans.find((c) => candidateName && candidateName.includes(c.name.replace('方案 ', ''))) || null
  if (!target) return null
  slot.selected_candidate_id = target.candidate_id
  slot.dishes = JSON.parse(JSON.stringify(target.dishes))
  slot.kcal = target.kcal
  recalcPlanKcal()
  state.currentPlan.status = 'draft'
  return { slot, candidate: target }
}

function findSlot(mealLabel) {
  const label = mealLabel || ''
  const day = state.currentPlan.days[0]
  if (!day) return null
  return (
    day.slots.find((s) => label.includes(s.label)) ||
    day.slots.find((s) => label.includes(s.meal_type)) ||
    null
  )
}

function recalcPlanKcal() {
  state.currentPlan.days.forEach((d) => {
    d.kcal = d.slots.reduce((s, x) => s + x.kcal, 0)
  })
}

/* ---------- 食材清单 / 报告 ---------- */
export function getShoppingList(mealPlanId) {
  const plan = mealPlanId ? getPlanById(mealPlanId) : state.currentPlan
  if (!plan || plan.status !== 'fixed') return null
  return buildShoppingList(plan)
}

export function getNutritionReport({ meal_plan_id, scope } = {}) {
  if (scope === 'week' || scope === 'month') {
    return state.reports.find((r) => r.scope === scope) || buildReport(scope)
  }
  // 没指定方案时，优先回已生成过的报告：对话里生成的那份要在右侧面板里能看到
  if (!meal_plan_id && state.reports.length) return state.reports[0]
  const plan = meal_plan_id ? getPlanById(meal_plan_id) : state.currentPlan
  if (!plan || plan.status !== 'fixed') return null
  return {
    report_id: `report_${plan.plan_id}`,
    scope: plan.plan_type,
    headline: `${plan.title} · 营养复盘`,
    meta: {
      scope: plan.plan_type,
      range_start: plan.days[0].date,
      range_end: plan.days[plan.days.length - 1].date,
      generated_at: plan.updated_at,
      valid_days: plan.days.length,
      total_meals: plan.days.reduce((s, d) => s + d.slots.length, 0),
      target_kcal: plan.goal_energy_kcal
    },
    summary_text: `覆盖 ${plan.days.length} 天，${plan.days.reduce((s, d) => s + d.slots.length, 0)} 餐；7 项关键微量按跨日动态平衡评估。`,
    ...plan.nutrition
  }
}

export function generateReport(scope) {
  const report = buildReport(scope)
  state.reports.unshift(report)
  return report
}

/* ---------- 结构化边车（SSE meta.blocks） ---------- */

export function slotView(slot) {
  return {
    slot_id: slot.slot_id,
    meal_type: slot.meal_type,
    label: slot.label,
    time: slot.time,
    color: slot.color,
    kcal: slot.kcal,
    oil_g: slot.oil_g,
    salt_g: slot.salt_g,
    dish_text: slot.dishes.map((d) => d.name).join(' + '),
    dish_count: slot.dishes.length,
    dishes: slot.dishes,
    candidates: (slot.candidates || []).map((c) => ({
      candidate_id: c.candidate_id,
      name: c.name,
      kcal: c.kcal,
      desc: c.desc,
      dishes: c.dishes
    })),
    selected_candidate_id: slot.selected_candidate_id,
    micro: slot.micro_coverage
  }
}

export function mealCardBlock(plan) {
  const isWeek = plan.plan_type === 'week'
  const goal = goalText(state.profile)
  const firstDay = plan.days[0]
  const avgKcal = Math.round(plan.days.reduce((s, d) => s + d.kcal, 0) / plan.days.length)
  const candidateCount = (firstDay.slots[0] && firstDay.slots[0].candidates ? firstDay.slots[0].candidates.length : 0)
  const subtitle = isWeek
    ? `目标：${goal} · ${plan.range_text} · 日均约 ${avgKcal} kcal`
    : plan.plan_type === 'meal'
      ? `目标：${goal} · 单餐约 ${firstDay.kcal} kcal · ${candidateCount} 个候选`
      : `目标：${goal} · 全天约 ${firstDay.kcal} kcal`
  return {
    type: 'meal_card',
    plan_id: plan.plan_id,
    card_id: `card_${plan.plan_id}`,
    title: isWeek ? '📅 一周食谱' : plan.plan_type === 'meal' ? '🍱 午餐搭配' : '🗓️ 今日食谱',
    subtitle,
    scope: plan.plan_type,
    status: plan.status === 'fixed' ? 'fixed' : plan.plan_type === 'meal' ? 'candidates' : 'draft',
    goal_text: plan.goal_text,
    target_kcal: plan.goal_energy_kcal,
    total_kcal: plan.days[0].kcal,
    range_text: plan.range_text,
    slots: isWeek ? [] : plan.days[0].slots.map(slotView),
    days: isWeek
      ? plan.days.map((d) => ({
          date: d.date,
          weekday: d.weekday,
          is_today: d.is_today,
          kcal: d.kcal,
          slots: d.slots.map(slotView)
        }))
      : [],
    reason: { summary: '按档案与近期微量摄入平衡排出这套方案', points: plan.reason_points },
    action_scope_label: plan.plan_type === 'week' ? '整周规划' : plan.plan_type === 'meal' ? '这一餐' : '规划'
  }
}

export function mealPlanBlock(plan, view) {
  return {
    type: 'meal_plan',
    plan_id: plan.plan_id,
    view: view || (plan.plan_type === 'week' ? 'week' : 'day'),
    title: plan.title,
    subtitle: plan.subtitle,
    days: plan.days.map((d) => ({
      date: d.date,
      weekday: d.weekday,
      is_today: d.is_today,
      kcal: d.kcal,
      slots: d.slots.map(slotView)
    }))
  }
}

export function nutritionBlock(plan) {
  return {
    type: 'nutrition',
    plan_id: plan.plan_id,
    ...plan.nutrition
  }
}

export function recipeBlock(plan) {
  return {
    type: 'recipe_detail',
    title: `${plan.title} · 详细食谱`,
    meals: plan.days[0].slots.map((s) => ({
      label: s.label,
      time: s.time,
      color: s.color,
      kcal: s.kcal,
      total: s.kcal,
      dishes: s.dishes.map((d) => ({
        name: d.name,
        amount: d.amount,
        kcal: d.kcal,
        tip: d.tip,
        steps: d.steps || []
      }))
    }))
  }
}

export function sourcesBlock() {
  return { type: 'sources', title: '参考来源', items: SOURCES }
}

export function anchorBlock(items) {
  return { type: 'anchor', items }
}

export function shoppingBlock(list) {
  const total = list.groups.reduce((s, g) => s + g.items.length, 0)
  return {
    type: 'shopping_list',
    title: '食材清单',
    summary: `共 ${total} 项，分 ${list.groups.length} 组`,
    groups: list.groups.slice(0, 12)
  }
}

export function reportBlock(report) {
  return { type: 'report', ...report, expanded: false }
}

export const DEMO_USER = {
  name: DEFAULT_PROFILE.extras.name,
  goal: goalText(DEFAULT_PROFILE),
  today: dayInfo(0)
}
