/**
 * v1.2 对象转换层：把演示用的计划/报告内容转成《Agent 输出契约 v1.2》的 payload。
 * 字段名严格按 v1.2：meal_plan_id / meal_slot_id / dish_id(text) / portion_text /
 * method_override / oil_salt_estimate / micro_estimate / plan_type / goal_code。
 * 本文件只做结构转换，不改数值口径。
 */
import { buildPlan, buildReport, buildShoppingList } from './data.js'

export const MICRO_KEYS = ['calcium', 'iron', 'zinc', 'vitamin_a', 'vitamin_b1', 'vitamin_b2', 'vitamin_c']
export const MICRO_META = {
  calcium: { name_zh: '钙', unit: 'mg', target: 800 },
  iron: { name_zh: '铁', unit: 'mg', target: 18 },
  zinc: { name_zh: '锌', unit: 'mg', target: 7.5 },
  vitamin_a: { name_zh: '维生素A', unit: 'μgRAE', target: 700 },
  vitamin_b1: { name_zh: '维生素B1', unit: 'mg', target: 1.2 },
  vitamin_b2: { name_zh: '维生素B2', unit: 'mg', target: 1.2 },
  vitamin_c: { name_zh: '维生素C', unit: 'mg', target: 100 }
}

const DISH_IDS = new Map()
let dishSeq = 1
function dishIdOf(name) {
  if (!DISH_IDS.has(name)) {
    DISH_IDS.set(name, `DISH-${String(dishSeq++).padStart(3, '0')}`)
  }
  return DISH_IDS.get(name)
}

function isStaple(name) {
  return /米|面|吐司|馒头|红薯|玉米|藜麦|燕麦|小米|麦|饼|面包/.test(name)
}

function gramsOf(amountText) {
  const m = String(amountText || '').match(/(\d+(?:\.\d+)?)\s*(g|ml|克|毫升)/i)
  if (m) return Number(m[1])
  return null
}

function macroOf(kcal) {
  if (kcal == null || !Number.isFinite(Number(kcal))) {
    return { kcal: null, protein_g: null, fat_g: null, carb_g: null, fiber_g: null }
  }
  const k = Number(kcal)
  return {
    kcal: k,
    protein_g: Math.round((k * 0.22) / 4),
    fat_g: Math.round((k * 0.28) / 9),
    carb_g: Math.round((k * 0.5) / 4),
    fiber_g: 5.6
  }
}

function microOf(kcal) {
  if (kcal == null) return null
  const ratio = Math.min(0.35, Math.max(0.12, Number(kcal) / 1600))
  const out = {}
  MICRO_KEYS.forEach((k) => {
    out[k] = Number((MICRO_META[k].target * ratio).toFixed(1))
  })
  return out
}

function toDish(d, order) {
  return {
    dish_id: dishIdOf(d.name),
    name: d.name,
    role: isStaple(d.name) ? '主食' : '菜',
    servings: 1,
    estimated_g: gramsOf(d.amount),
    portion_text: d.amount || null,
    method_override: null,
    display_order: order
  }
}

/** 旧演示计划 → v1.2 MealCard payload */
export function planToMealCard(legacy, planId) {
  const slots = []
  legacy.days.forEach((day, di) => {
    day.slots.forEach((slot, si) => {
      const mealSlotId = planId * 100 + di * 10 + si + 1
      // 候选 1 = 当天模板搭配（保证每天不重样），候选 2/3 = 换候选池里真正不同的搭配
      const selfName = slot.dishes.map((d) => d.name).join('|')
      const pool = slot.candidates
        .filter((c) => c.dishes.map((d) => d.name).join('|') !== selfName)
        .slice(0, 2)
      const rawCandidates = [
        {
          name: slot.dishes.map((d) => d.name).join(' + '),
          kcal: slot.kcal,
          desc: '按当天目标搭配，油盐已单独核算',
          dishes: slot.dishes
        },
        ...pool
      ]
      const candidates = rawCandidates.map((c, ci) => {
        const candidateId = mealSlotId * 10 + ci + 1
        return {
          candidate_id: candidateId,
          rank: ci + 1,
          why_text: c.desc,
          reason_codes: ci === 0 ? ['goal_energy_match', 'protein_supply'] : ['protein_supply'],
          macro_estimate: macroOf(c.kcal),
          micro_estimate: microOf(c.kcal),
          oil_salt_estimate: {
            oil_g: slot.oil_g == null ? null : slot.oil_g,
            salt_g: slot.salt_g == null ? null : slot.salt_g
          },
          eating_order_advice: '先吃蔬菜与蛋白，再吃主食，细嚼慢咽',
          sources: [{ type: 'ingredient', food_id: 'CN-1001' }],
          dishes: (c.dishes || []).map((d, i) => toDish(d, i + 1))
        }
      })
      const selected = candidates[0] ? candidates[0].candidate_id : null
      slots.push({
        meal_slot_id: mealSlotId,
        slot_date: day.iso,
        meal_type: slot.meal_type === 'breakfast' ? '早' : slot.meal_type === 'dinner' ? '晚' : '午',
        display_order: si + 1,
        target_macro: macroOf(slot.kcal),
        selected_candidate_id: selected,
        candidates
      })
    })
  })

  const planTypeMap = { week: '周', meal: '餐', day: '日', multi: '多日', custom: '自定义' }
  return {
    meal_plan_id: planId,
    plan_type: planTypeMap[legacy.plan_type] || '日',
    status: legacy.status === 'fixed' ? 'fixed' : 'candidates',
    start_date: legacy.days[0].iso,
    end_date: legacy.days[legacy.days.length - 1].iso,
    goal_code: legacy.goal_code || 'fat_loss',
    goal_energy_kcal: legacy.goal_energy_kcal || 1850,
    macro_ratio: { 早: 0.3, 午: 0.4, 晚: 0.3 },
    slots,
    why_summary: '按档案与近期微量摄入平衡排出这套方案，油盐单独核算，主食优先粗粮。',
    reference_hints: ['本期铁按普通口径计算，未区分经期'],
    data_quality_notes: ['部分食材微量为近似值（approx/check），不作为官方实测结论']
  }
}

/** 旧演示计划 → v1.2 CurrentPlan payload */
export function planToCurrentPlan(card) {
  return {
    has_plan: true,
    meal_plan_id: card.meal_plan_id,
    plan_type: card.plan_type,
    status: card.status === 'fixed' ? 'fixed' : 'candidates',
    start_date: card.start_date,
    end_date: card.end_date,
    fixed_at: card.status === 'fixed' ? new Date().toISOString() : null,
    goal_energy_kcal: card.goal_energy_kcal,
    slots: card.slots.map((s) => {
      const selected = s.candidates.find((c) => c.candidate_id === s.selected_candidate_id) || s.candidates[0]
      return {
        meal_slot_id: s.meal_slot_id,
        slot_date: s.slot_date,
        meal_type: s.meal_type,
        display_order: s.display_order,
        selected_candidate_id: s.selected_candidate_id,
        dish_ids: selected ? selected.dishes.map((d) => d.dish_id) : [],
        dish_names: selected ? selected.dishes.map((d) => d.name) : [],
        kcal: selected ? selected.macro_estimate.kcal : null
      }
    })
  }
}

const CATEGORY_MAP = {
  蔬菜类: '蔬菜',
  肉禽蛋水产: '肉类',
  主食杂粮: '主食谷物',
  水果坚果: '水果',
  奶豆饮品: '蛋奶',
  其他: '其他'
}

/** 旧清单 → v1.2 ShoppingList payload（不含 is_staple） */
export function planToShoppingList(legacy, planId) {
  const groups = legacy.groups.map((g, gi) => {
    const key = String(g.category || '').replace(/[^\u4e00-\u9fa5]/g, '').replace('类', '')
    return {
      category: CATEGORY_MAP[key] || '其他',
      items: g.items.map((it, ii) => ({
        ingredient_id: `CN-${1000 + gi * 20 + ii}`,
        name: it.name,
        estimated_quantity: gramsOf(it.amount),
        unit: gramsOf(it.amount) == null ? '份' : /ml|毫升/i.test(it.amount) ? 'ml' : 'g'
      }))
    }
  })
  return {
    shopping_list_id: planId * 10 + 1,
    meal_plan_id: planId,
    total_items: groups.reduce((s, g) => s + g.items.length, 0),
    groups,
    generated_at: new Date().toISOString()
  }
}

/** 旧报告 → v1.2 NutritionReport payload */
export function toNutritionReport(legacy, { planId, reportId, windowDays = 7 } = {}) {
  const merged = new Map()
  legacy.micro.items.forEach((it) => {
    const key = MICRO_KEYS.find((k) => MICRO_META[k].name_zh === it.name) || 'calcium'
    if (!merged.has(key)) merged.set(key, it)
  })
  const keyMicro = {}
  MICRO_KEYS.forEach((k) => {
    const meta = MICRO_META[k]
    const it = merged.get(k)
    const pct = it ? Number(it.ring_percent) : null
    const intake = pct == null ? null : Number((meta.target * pct / 100).toFixed(1))
    const status = pct == null ? '参考提示' : pct >= 100 ? '达标' : pct >= 70 ? '参考提示' : '不足'
    keyMicro[k] = {
      name_zh: meta.name_zh,
      target: meta.target,
      unit: meta.unit,
      intake,
      gap: intake == null ? null : Number((intake - meta.target).toFixed(1)),
      covered_pct: pct,
      status
    }
  })

  const seg = legacy.macro.segments
  return {
    nutrition_report_id: reportId,
    report_type: 'plan',
    meal_plan_id: planId,
    period_start: legacy.meta.range_start,
    period_end: legacy.meta.range_end,
    window_days: windowDays,
    macro_summary: {
      energy_kcal: Number(legacy.macro.center_value) || null,
      protein_pct: seg[0] ? seg[0].percent : null,
      fat_pct: seg[2] ? seg[2].percent : null,
      carb_pct: seg[1] ? seg[1].percent : null,
      oil_g: 24,
      salt_g: 5.2,
      fiber_g: 26
    },
    key_micro_summary: keyMicro,
    summary: {
      reference_hints: [...legacy.insights, '铁按普通口径计算，未区分经期（本期口径）'],
      data_quality_notes: ['部分食材微量为近似值（approx/check），不作为官方实测结论']
    },
    completeness: {
      meal_count: legacy.meta.total_meals,
      known_meal_count: legacy.meta.total_meals,
      missing_meal_count: 0
    },
    sources: [{ type: 'goal_structure_map', version: 'product-v2.0' }],
    generated_at: new Date().toISOString()
  }
}

/** 生成一份演示计划（不落库），仅给 mock 内部使用 */
export function makeLegacyPlan(planType) {
  return buildPlan(planType)
}

export { buildReport, buildShoppingList }
