/**
 * Mock 状态机（v1.2）：档案 11 字段、方案状态机、清单与报告。
 * 返回体一律 { code, message, data }，data 直接是对象（列表为分页结构）。
 */
import {
  planToMealCard,
  planToCurrentPlan,
  planToShoppingList,
  toNutritionReport,
  makeLegacyPlan,
  buildReport
} from './v12.js'

const GOALS = ['maintain', 'fat_loss', 'muscle_gain', 'glucose_control', 'digestive_health']
export const GOAL_NAMES = {
  maintain: '维持',
  fat_loss: '减脂',
  muscle_gain: '增肌',
  glucose_control: '控糖',
  digestive_health: '改善肠胃'
}
export const CONDITION_IDS = ['hypertension', 'diabetes', 'hyperlipidemia', 'gout']
export const CONDITION_NAMES = {
  hypertension: '高血压',
  diabetes: '糖尿病',
  hyperlipidemia: '高血脂',
  gout: '痛风'
}

function bmrTarget(p) {
  const isFemale = p.gender !== '男'
  const bmr = 10 * Number(p.weight_kg) + 6.25 * Number(p.height_cm) - 5 * Number(p.age) + (isFemale ? -161 : 5)
  return Math.round((bmr * 1.4) / 10) * 10
}

const DEFAULT_PROFILE = {
  user_id: 'demo-user',
  name: '小膳',
  avatar: '🍃',
  gender: '女',
  age: 26,
  height_cm: 158,
  weight_kg: 58,
  goal_code: 'fat_loss',
  goal_name: GOAL_NAMES.fat_loss,
  cooking_equipment: ['电饭煲', '炒锅'],
  conditions: {
    hypertension: { status: 'confirmed' },
    diabetes: { status: 'unknown' },
    hyperlipidemia: { status: 'unknown' },
    gout: { status: 'unknown' }
  },
  allergies: ['花生'],
  religious_ethical: [],
  target_calories: 0
}
DEFAULT_PROFILE.target_calories = bmrTarget(DEFAULT_PROFILE)

export const state = {
  profile: JSON.parse(JSON.stringify(DEFAULT_PROFILE)),
  plans: [],
  currentPlanId: null,
  planSeq: 101
}

/** 仅 mock 联调使用：把内存状态清回初始值 */
export function resetState() {
  state.profile = JSON.parse(JSON.stringify(DEFAULT_PROFILE))
  state.plans = []
  state.currentPlanId = null
  state.planSeq = 101
  return { ok: true }
}

/* ---------------- 档案 ---------------- */

export function getProfile() {
  return state.profile
}

export function normalizeConditions(input) {
  const out = {}
  CONDITION_IDS.forEach((id) => {
    const raw = input && input[id]
    const status = raw && (typeof raw === 'string' ? raw : raw.status)
    out[id] = { status: ['confirmed', 'suspected', 'unknown'].includes(status) ? status : 'unknown' }
  })
  return out
}

export function saveProfile(payload) {
  const next = { ...state.profile }
  const writable = [
    'name', 'avatar', 'gender', 'age', 'height_cm', 'weight_kg',
    'goal_code', 'cooking_equipment', 'allergies', 'religious_ethical'
  ]
  writable.forEach((k) => {
    if (payload[k] !== undefined) next[k] = payload[k]
  })
  if (payload.conditions !== undefined) next.conditions = normalizeConditions(payload.conditions)
  next.gender = next.gender === '男' ? '男' : '女'
  next.goal_name = GOAL_NAMES[next.goal_code] || ''
  next.cooking_equipment = Array.isArray(next.cooking_equipment) ? next.cooking_equipment : []
  next.allergies = Array.isArray(next.allergies) ? next.allergies.filter((x) => x && x !== '无') : []
  next.religious_ethical = Array.isArray(next.religious_ethical) ? next.religious_ethical.filter((x) => x && x !== '无') : []
  // 只读字段：target_calories 由后端按 BMR×1.4 计算，忽略请求体里的值
  next.target_calories = bmrTarget(next)
  state.profile = next
  return next
}

/* ---------------- 方案 ---------------- */

function adjustDates(legacy, startDate, dayCount) {
  const base = startDate ? new Date(`${startDate}T00:00:00`) : new Date()
  legacy.days = legacy.days.slice(0, dayCount).map((d, i) => {
    const dt = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i)
    const iso = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
    const md = iso.slice(5)
    const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][dt.getDay()]
    return { ...d, iso, date: md, weekday: week, is_today: i === 0 }
  })
  legacy.days.forEach((d) => {
    d.kcal = d.slots.reduce((s, x) => s + (Number(x.kcal) || 0), 0)
  })
  return legacy
}

function rangePlanType(start, end) {
  const s = new Date(`${start}T00:00:00`)
  const e = new Date(`${end}T00:00:00`)
  const days = Math.round((e - s) / 86400000) + 1
  if (start === end) return '日'
  if (days <= 3) return '多日'
  if (days === 7) return '周'
  return '自定义'
}

export function createPlan({ start_date, end_date, plan_type, goal_code, candidates_per_slot, meal_types }) {
  const start = start_date
  const end = end_date
  const s = new Date(`${start}T00:00:00`)
  const e = new Date(`${end}T00:00:00`)
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return { error: { code: 1001, message: '日期格式不合法' } }
  if (e < s) return { error: { code: 1001, message: 'end_date 不能早于 start_date' } }
  const days = Math.round((e - s) / 86400000) + 1
  if (days > 31) return { error: { code: 1001, message: '方案跨度上限 31 天' } }

  const type = plan_type || rangePlanType(start, end)
  if (!['餐', '日', '多日', '周', '自定义'].includes(type)) {
    return { error: { code: 1001, message: 'plan_type 取值非法' } }
  }
  if (candidates_per_slot != null) {
    const n = Number(candidates_per_slot)
    if (!Number.isInteger(n) || n < 2 || n > 3) {
      return { error: { code: 1001, message: 'candidates_per_slot 需在 2～3 之间' } }
    }
  }
  if (meal_types != null && (!Array.isArray(meal_types) || !meal_types.length || meal_types.some((t) => !['早', '午', '晚'].includes(t)))) {
    return { error: { code: 1001, message: 'meal_types 仅支持 早/午/晚 且不能为空' } }
  }

  // 内容按跨度取模板：单餐用午餐模板，多日/周用周模板，日/自定义按天
  const templateType = type === '餐' ? 'meal' : type === '日' ? 'day' : 'week'
  const legacy = makeLegacyPlan(templateType)
  adjustDates(legacy, start, Math.max(1, days))
  legacy.plan_type = type === '餐' ? 'meal' : type === '周' ? 'week' : type === '多日' ? 'multi' : 'day'
  legacy.status = 'candidates'
  legacy.goal_code = goal_code || state.profile.goal_code
  legacy.goal_energy_kcal = state.profile.target_calories

  const planId = state.planSeq++
  const card = planToMealCard(legacy, planId)
  card.plan_type = type
  if (meal_types) card.slots = card.slots.filter((s) => meal_types.includes(s.meal_type))
  if (candidates_per_slot != null) {
    const n = Number(candidates_per_slot)
    for (const slot of card.slots) {
      slot.candidates = slot.candidates.slice(0, n)
      if (!slot.candidates.some((c) => c.candidate_id === slot.selected_candidate_id)) {
        slot.selected_candidate_id = slot.candidates[0]?.candidate_id ?? null
      }
    }
  }
  const record = {
    id: planId,
    card,
    legacy,
    created_at: new Date().toISOString(),
    fixed_at: null
  }
  state.plans.unshift(record)
  state.currentPlanId = planId
  return { plan: card, record }
}

export function findRecord(planId) {
  return state.plans.find((p) => String(p.id) === String(planId)) || null
}

export function currentPlanRecord() {
  const fixed = state.plans.find((p) => p.card.status === 'fixed')
  if (fixed) return fixed
  const candidates = state.plans.find((p) => p.card.status === 'candidates')
  return candidates || null
}

export function getCurrentPlanPayload() {
  const record = currentPlanRecord()
  if (!record) return null
  return planToCurrentPlan(record.card)
}

export function getPlanPayload(planId) {
  const record = findRecord(planId)
  return record ? record.card : null
}

export function listPlans({ page = 1, page_size = 20, status } = {}) {
  let list = state.plans.slice()
  if (status) list = list.filter((p) => p.card.status === status)
  const total = list.length
  const p = Math.max(1, Number(page) || 1)
  const size = Math.min(100, Math.max(1, Number(page_size) || 20))
  const items = list.slice((p - 1) * size, p * size).map((r) => ({
    meal_plan_id: r.id,
    plan_type: r.card.plan_type,
    status: r.card.status,
    start_date: r.card.start_date,
    end_date: r.card.end_date,
    goal_energy_kcal: r.card.goal_energy_kcal,
    created_at: r.created_at,
    fixed_at: r.fixed_at
  }))
  return { total, page: p, page_size: size, items }
}

export function swapCandidate({ meal_plan_id, meal_slot_id, candidate_id }) {
  const record = findRecord(meal_plan_id)
  if (!record) return { error: { code: 1004, message: '方案不存在' } }
  if (record.card.status === 'fixed') {
    return { error: { code: 2005, message: '方案已固定，不能再换候选' } }
  }
  const slot = record.card.slots.find((s) => String(s.meal_slot_id) === String(meal_slot_id))
  if (!slot) return { error: { code: 1004, message: '餐位不存在' } }
  const current = slot.candidates.find((c) => c.candidate_id === slot.selected_candidate_id) || slot.candidates[0]
  let next
  if (candidate_id != null) {
    next = slot.candidates.find((c) => String(c.candidate_id) === String(candidate_id))
    if (!next) return { error: { code: 2005, message: '候选不属于该餐位' } }
  } else {
    const idx = slot.candidates.indexOf(current)
    next = slot.candidates[(idx + 1) % slot.candidates.length]
  }
  if (!next || next.candidate_id === current.candidate_id) {
    return { error: { code: 2006, message: '该餐位没有可替换的候选' } }
  }
  slot.selected_candidate_id = next.candidate_id
  return {
    meal_plan_id: record.id,
    meal_slot_id: slot.meal_slot_id,
    selected_candidate_id: next.candidate_id,
    candidate: next,
    macro_delta: {
      kcal: (next.macro_estimate.kcal || 0) - (current.macro_estimate.kcal || 0),
      protein_g: (next.macro_estimate.protein_g || 0) - (current.macro_estimate.protein_g || 0)
    }
  }
}

export function fixPlan({ meal_plan_id, selections }) {
  const record = findRecord(meal_plan_id)
  if (!record) return { error: { code: 1004, message: '方案不存在' } }
  if (record.card.status === 'fixed') {
    return { error: { code: 2005, message: '方案已固定，无需重复固定' } }
  }
  if (Array.isArray(selections) && selections.length) {
    for (const sel of selections) {
      const slot = record.card.slots.find((s) => String(s.meal_slot_id) === String(sel.meal_slot_id))
      if (!slot) return { error: { code: 1001, message: 'selections 中的餐位不存在' } }
      if (!slot.candidates.some((c) => String(c.candidate_id) === String(sel.candidate_id))) {
        return { error: { code: 2005, message: '候选不属于该餐位' } }
      }
      slot.selected_candidate_id = sel.candidate_id
    }
  }
  const missing = record.card.slots.filter((s) => !s.selected_candidate_id)
  if (missing.length) {
    return { error: { code: 2005, message: '还有餐位未选择候选，不能固定' } }
  }
  record.card.status = 'fixed'
  record.fixed_at = new Date().toISOString()
  return record.card
}

/* ---------------- 清单 / 报告 ---------------- */

export function getShoppingListPayload(planId) {
  const record = findRecord(planId)
  if (!record) return { error: { code: 1004, message: '方案不存在' } }
  if (record.card.status !== 'fixed') {
    return { error: { code: 2005, message: '方案未固定，清单未生成' } }
  }
  if (!record.shopping) {
    const legacyList = {
      groups: []
    }
    const byGroup = []
    record.legacy.days.forEach((day, di) => {
      day.slots.forEach((slot) => {
        (slot.candidates || []).slice(0, 1).forEach((c) => {
          (c.dishes || []).forEach((d) => {
            const cat = /菜|瓜|茄|椒|芦笋|木耳|海带|菌|菇|笋|菠菜|芥蓝|空心菜|油麦菜|娃娃菜|包菜|番茄|西兰花|萝卜|白菜/.test(d.name)
              ? '蔬菜类'
              : /鸡|牛|猪|鱼|虾|肉|排|三文鱼|鳕鱼|鲈鱼|龙利鱼|鸡胸|鸡腿|排骨|蛋/.test(d.name)
                ? '肉禽蛋水产'
                : /米|面|吐司|馒头|红薯|玉米|藜麦|燕麦|小米|麦|饼|面包/.test(d.name)
                  ? '主食杂粮'
                  : /豆浆|酸奶|牛奶|豆腐|豆/.test(d.name)
                    ? '奶豆饮品'
                    : '其他'
            let g = byGroup.find((x) => x.category === cat)
            if (!g) {
              g = { category: cat, items: [] }
              byGroup.push(g)
            }
            if (!g.items.some((x) => x.name === d.name)) {
              g.items.push({ name: d.name, amount: d.portion_text || d.amount })
            }
          })
        })
      })
    })
    legacyList.groups = byGroup
    record.shopping = planToShoppingList({ groups: byGroup, updated_at: record.fixed_at }, record.id)
  }
  return record.shopping
}

export function reportForPlan(planId, { window_days = 7 } = {}) {
  const record = findRecord(planId)
  if (!record) return { error: { code: 1004, message: '方案不存在' } }
  if (!record.report) {
    const legacyReport = buildReport('week')
    record.report = toNutritionReport(legacyReport, { planId: record.id, reportId: record.id + 900, windowDays: window_days })
    record.report.period_start = record.card.start_date
    record.report.period_end = record.card.end_date
    const slotCount = record.card.slots.length
    record.report.completeness = {
      meal_count: slotCount,
      known_meal_count: slotCount,
      missing_meal_count: 0
    }
  }
  return record.report
}

export function getReportPayload(planId) {
  const record = findRecord(planId)
  if (!record) return { error: { code: 1004, message: '方案不存在' } }
  if (!record.report) return { error: { code: 1004, message: '该方案还没有生成报告' } }
  return record.report
}

/* ---------------- 演示数据 ---------------- */

export const DEMO = {
  GOALS,
  GOAL_NAMES,
  CONDITION_IDS,
  CONDITION_NAMES
}
