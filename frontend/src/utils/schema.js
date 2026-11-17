/**
 * schema 适配层（v1.2）：唯一字段源为《Agent 输出契约 v1.2》。
 * 上游 payload → 渲染视图模型（视图模型只做展示派生，不补算营养数值）。
 * 数值铁律：null = 未知，视图里保留 null，由组件渲染「—」/「暂无数据」。
 */

export function pick(obj, ...keys) {
  if (!obj || typeof obj !== 'object') return undefined
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k]
  }
  return undefined
}

/** 只接受确实存在的数值，null / 缺字段 / 空串都返回 null，绝不回落 0 */
export function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export function arr(v) {
  return Array.isArray(v) ? v : []
}

export function str(v, fallback = '') {
  return typeof v === 'string' ? v : v == null ? fallback : String(v)
}

export function fmtNum(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return String(n)
}

export function fmtPct(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n * 10) / 10}%`
}

/* 热量（kcal）统一保留 1 位小数 */
export function fmtKcal(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(1)
}

/* ---------- 枚举展示（只做中文标签，不承载业务映射表） ---------- */

const MEAL_LABELS = { 早: '早餐', 午: '午餐', 晚: '晚餐' }
const MEAL_TIMES = { 早: '07:30', 午: '12:00', 晚: '18:30' }
const MEAL_COLORS = { 早: '#e8942c', 午: '#4a7c59', 晚: '#3b7fd4' }
const PLAN_TYPES = { 餐: 'meal', 日: 'day', 多日: 'multi', 周: 'week', 自定义: 'custom' }
const PLAN_TITLES = { 餐: '一餐搭配', 日: '今日三餐', 多日: '多日方案', 周: '一周食谱', 自定义: '自定义方案' }
export const STATUS_LABELS = { draft: '草稿', candidates: '待确认', fixed: '已生效', superseded: '已取代' }

export const GOAL_LABELS = {
  maintain: '维持',
  fat_loss: '减脂',
  muscle_gain: '增肌',
  glucose_control: '控糖',
  digestive_health: '改善肠胃'
}

export function goalLabel(code) {
  return (code && GOAL_LABELS[code]) || ''
}

export function planTypeKey(v) {
  return PLAN_TYPES[v] || 'day'
}

export function planTypeTitle(v) {
  return PLAN_TITLES[v] || '膳食方案'
}

export function mealLabel(v) {
  return MEAL_LABELS[v] || str(v, '餐次')
}

/* ---------- 菜品 / 候选 / 餐位 ---------- */

function dishView(d) {
  const estimated = numOrNull(pick(d, 'estimated_g'))
  return {
    dish_id: str(pick(d, 'dish_id'), ''),
    name: str(pick(d, 'name'), '未命名菜品'),
    role: str(pick(d, 'role'), ''),
    amount: str(pick(d, 'portion_text'), '') || (estimated === null ? '—' : `约 ${estimated} g`),
    kcal: null,
    // 做法要点：method_override（换做法覆盖）优先，缺省回落到 core.dish 的 method_text
    tip: str(pick(d, 'method_override', 'method_text'), ''),
    ingredients: arr(pick(d, 'ingredients')),
    steps: arr(pick(d, 'steps')),
    display_order: numOrNull(pick(d, 'display_order')) || 0
  }
}

function candidateView(c, i) {
  const dishes = arr(c && c.dishes).map(dishView)
  const macro = (c && c.macro_estimate) || {}
  const oilSalt = (c && c.oil_salt_estimate) || {}
  return {
    candidate_id: str(pick(c, 'candidate_id'), `c${i}`),
    rank: numOrNull(pick(c, 'rank')) || i + 1,
    name: dishes.map((d) => d.name).join(' + ') || `候选 ${i + 1}`,
    kcal: numOrNull(pick(macro, 'kcal')),
    protein_g: numOrNull(pick(macro, 'protein_g')),
    fat_g: numOrNull(pick(macro, 'fat_g')),
    carb_g: numOrNull(pick(macro, 'carb_g')),
    fiber_g: numOrNull(pick(macro, 'fiber_g')),
    desc: str(pick(c, 'why_text'), ''),
    reason_codes: arr(pick(c, 'reason_codes')),
    oil_g: numOrNull(pick(oilSalt, 'oil_g')),
    salt_g: numOrNull(pick(oilSalt, 'salt_g')),
    advice: str(pick(c, 'eating_order_advice'), ''),
    dishes
  }
}

/**
 * v1.2 MealCard slot → 视图 slot
 * slot: meal_slot_id / slot_date / meal_type / display_order / target_macro /
 *       selected_candidate_id / candidates[]
 */
export function normalizeSlot(slot) {
  const s = slot || {}
  const candidates = arr(s.candidates).map(candidateView)
  const selectedId = pick(s, 'selected_candidate_id')
  const selected =
    candidates.find((c) => String(c.candidate_id) === String(selectedId)) || candidates[0] || null
  const target = s.target_macro || {}
  const dishes = selected ? selected.dishes : []
  const meal = str(pick(s, 'meal_type'), '午')
  return {
    slot_id: str(pick(s, 'meal_slot_id', 'slot_id'), ''),
    meal_type: meal,
    label: mealLabel(meal),
    time: MEAL_TIMES[meal] || '',
    color: MEAL_COLORS[meal] || 'var(--brand)',
    slot_date: str(pick(s, 'slot_date'), ''),
    display_order: numOrNull(pick(s, 'display_order')) || 0,
    kcal: selected ? selected.kcal : numOrNull(pick(target, 'kcal')),
    target_kcal: numOrNull(pick(target, 'kcal')),
    protein_g: selected ? selected.protein_g : numOrNull(pick(target, 'protein_g')),
    oil_g: selected ? selected.oil_g : null,
    salt_g: selected ? selected.salt_g : null,
    dishes,
    dish_text: dishes.map((d) => d.name).join(' + '),
    dish_count: numOrNull(pick(s, 'dish_count')) || dishes.length,
    candidates,
    selected_candidate_id: selected ? selected.candidate_id : '',
    micro: []
  }
}

function sortSlots(slots) {
  return slots.slice().sort((a, b) => {
    if (a.slot_date !== b.slot_date) return a.slot_date < b.slot_date ? -1 : 1
    return a.display_order - b.display_order
  })
}

function sumKnown(list) {
  const nums = list.filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
  if (!nums.length) return null
  return nums.reduce((s, v) => s + Number(v), 0)
}

function weekdayOf(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return ''
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
}

function mdOf(iso) {
  return iso ? iso.slice(5) : ''
}

function todayIso() {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function dayLabelOf(iso) {
  if (!iso) return ''
  if (iso === todayIso()) return '今天'
  return weekdayOf(iso)
}

function groupDays(slots) {
  const map = new Map()
  slots.forEach((s) => {
    if (!map.has(s.slot_date)) map.set(s.slot_date, [])
    map.get(s.slot_date).push(s)
  })
  return [...map.entries()].map(([iso, list]) => ({
    date: mdOf(iso),
    iso,
    weekday: weekdayOf(iso),
    is_today: iso === todayIso(),
    kcal: sumKnown(list.map((s) => s.kcal)),
    slots: sortSlots(list)
  }))
}

/* ---------- MealCard ---------- */

export function normalizeMealCard(payload) {
  const p = payload || {}
  const planType = str(pick(p, 'plan_type'), '日')
  const slots = arr(p.slots).map(normalizeSlot)
  const days = groupDays(slots)
  return {
    type: 'meal_card',
    raw_id: str(pick(p, 'meal_plan_id'), ''),
    plan_type: planType,
    plan_key: planTypeKey(planType),
    scope: planTypeKey(planType),
    scope_label: planTypeTitle(planType),
    title: planTypeTitle(planType),
    status: str(pick(p, 'status'), 'draft'),
    status_label: STATUS_LABELS[str(pick(p, 'status'), 'draft')] || '草稿',
    is_executed: Boolean(pick(p, 'is_executed')),
    start_date: str(pick(p, 'start_date'), ''),
    end_date: str(pick(p, 'end_date'), ''),
    range_text:
      pick(p, 'start_date') && pick(p, 'end_date')
        ? `${pick(p, 'start_date')} ~ ${pick(p, 'end_date')}`
        : '',
    goal_code: str(pick(p, 'goal_code'), ''),
    goal_energy_kcal: numOrNull(pick(p, 'goal_energy_kcal')),
    macro_ratio: p.macro_ratio || null,
    subtitle: planType === '餐'
      ? `目标 ${fmtNum(pick(p, 'goal_energy_kcal'))} kcal · 单餐候选`
      : pick(p, 'goal_energy_kcal')
        ? `目标 ${fmtNum(pick(p, 'goal_energy_kcal'))} kcal · 共 ${days.length} 天`
        : `共 ${days.length} 天`,
    slots,
    days,
    reason: str(pick(p, 'why_summary'), ''),
    reference_hints: arr(pick(p, 'reference_hints')),
    data_quality_notes: arr(pick(p, 'data_quality_notes'))
  }
}

/* ---------- CurrentPlan ---------- */

export function normalizeCurrentPlan(payload) {
  const p = payload || {}
  // 真后端 /meal-plan/current 返回 _serialize_plan（无 has_plan 字段），以 meal_plan_id 判有无方案
  const hasPlan = pick(p, 'meal_plan_id') != null
  if (!hasPlan) {
    return { type: 'current_plan', has_plan: false, plan: null }
  }
  const planType = str(pick(p, 'plan_type'), '日')
  const slots = arr(p.slots).map((s) => {
    // 真后端：槽位带 candidates → 走标准 normalizeSlot（含菜名/热量）
    if (arr(s.candidates).length) return normalizeSlot(s)
    // 旧 Mock 扁平结构（dish_names/dish_ids/kcal），保留兼容，待 Mock 对齐后端结构后删除
    const view = normalizeSlot({ ...s, candidates: [] })
    const names = arr(pick(s, 'dish_names')).map((n) => str(n))
    const kcal = numOrNull(pick(s, 'kcal'))
    return {
      ...view,
      kcal,
      dishes: names.map((name, i) => ({
        dish_id: str(arr(pick(s, 'dish_ids'))[i], ''),
        name,
        role: '',
        amount: '',
        kcal: null,
        tip: '',
        steps: []
      })),
      dish_text: names.join(' + '),
      dish_count: names.length
    }
  })
  const days = groupDays(slots)
  return {
    type: 'current_plan',
    has_plan: true,
    plan: {
      has_plan: true,
      plan_id: str(pick(p, 'meal_plan_id'), ''),
      plan_type: planType,
      status: str(pick(p, 'status'), 'draft'),
      title: planTypeTitle(planType),
      range_text:
        pick(p, 'start_date') && pick(p, 'end_date') ? `${pick(p, 'start_date')} ~ ${pick(p, 'end_date')}` : '',
      goal_energy_kcal: numOrNull(pick(p, 'goal_energy_kcal')),
      fixed_at: str(pick(p, 'fixed_at'), ''),
      days,
      slots,
      reason_points: [],
      sources: []
    }
  }
}

/* ---------- ShoppingList ---------- */

export function normalizeGroups(groups) {
  return arr(groups).map((g, gi) => {
    const dayDate = str(pick(g, 'day_date'), '')
    return {
      group_id: str(pick(g, 'group_id'), `g${gi}`),
      category: str(pick(g, 'category'), '其他'),
      day_date: dayDate,
      day: dayLabelOf(dayDate),
      day_short: mdOf(dayDate),
      items: arr(g.items).map((it, ii) => {
        const qty = numOrNull(pick(it, 'estimated_quantity'))
        const unit = str(pick(it, 'unit'), '')
        const preset = str(pick(it, 'amount'), '')
        const baseId = str(pick(it, 'ingredient_id') || pick(it, 'item_id'), `it${gi}${ii}`)
        return {
          // 同食材跨天重复出现时用 day_date 后缀保证勾选键唯一（周/多日按天分列）
          item_id: dayDate ? `${baseId}@${dayDate}` : baseId,
          name: str(pick(it, 'name'), ''),
          amount: preset || (qty === null ? '估算量待补' : `${fmtNum(qty)} ${unit}`.trim()),
          checked: false
        }
      })
    }
  })
}

/* ---------- NutritionReport ---------- */

const MICRO_KEYS = ['calcium', 'iron', 'zinc', 'vitamin_a', 'vitamin_b1', 'vitamin_b2', 'vitamin_c']
const MICRO_STATUS = { 达标: 'ok', 不足: 'warn', 超标: 'danger', 参考提示: 'neutral' }

function microView(entry, key) {
  const m = entry || {}
  const pct = numOrNull(pick(m, 'covered_pct'))
  const intake = numOrNull(pick(m, 'intake'))
  const statusZh = str(pick(m, 'status'), '')
  const unit = str(pick(m, 'unit'), '')
  const gap = numOrNull(pick(m, 'gap'))
  const ul = numOrNull(pick(m, 'ul'))
  const covered = numOrNull(pick(m, 'covered_meals'))
  const total = numOrNull(pick(m, 'selected_meals'))

  // 三档：无数据 / 部分数据（已知餐次的下限估算）/ 完整数据。
  // 部分数据仍不判达标/超标（null≠0），只展示「至少 X%」+ 覆盖率，避免一缺就整项清空。
  let level
  if (intake === null) level = 'none'
  else if (pct == null) level = 'none' // 有摄入但缺参考值，无法算覆盖度
  else if (covered != null && total != null) level = covered >= total ? 'full' : 'partial'
  else level = statusZh === '参考提示' ? 'partial' : 'full'

  let note
  let value
  let status
  if (level === 'none') {
    note = intake === null ? '数据不足' : '参考值缺失'
    value = '—'
    status = 'neutral'
  } else if (level === 'partial') {
    value = `≥${fmtPct(pct)}`
    note = covered != null && total != null ? `覆盖 ${covered}/${total} 餐` : '部分餐次缺数据'
    status = 'partial'
  } else {
    // 达标/不足/超标由 status_zh 决定：超标只看是否超过每日上限（UL），
    // 超过推荐量（>100%）但未超 UL 仍算达标，避免把「吃够了」误报成「超标」。
    if (statusZh === '超标') note = ul != null ? `超过每日上限 ${fmtNum(ul)}${unit}` : '超过每日上限'
    else if (statusZh === '不足') note = gap != null ? `还差 ${fmtNum(-gap)}${unit}` : '未达标'
    else note = '已达标'
    value = fmtPct(pct)
    status = MICRO_STATUS[statusZh] || 'neutral'
  }

  return {
    key,
    name: str(pick(m, 'name_zh'), key),
    target: numOrNull(pick(m, 'target')),
    ul,
    unit,
    intake,
    gap,
    percent: level === 'none' ? null : pct,
    value,
    status,
    status_zh: statusZh,
    level,
    covered_meals: covered,
    selected_meals: total,
    note
  }
}

const MACRO_LEVEL_TAG = { ok: '达标', warn: '注意', low: '偏低', high: '偏高' }

function macroSegment(name, pct, color, level, range) {
  const p = numOrNull(pct)
  const lv = typeof level === 'string' && level ? level : ''
  const rangeText =
    Array.isArray(range) && range.length === 2 ? `${range[0]}~${range[1]}%` : ''
  return {
    name,
    percent: p,
    color,
    tag: p === null ? '暂无数据' : MACRO_LEVEL_TAG[lv] || '',
    tag_level:
      lv === 'ok' ? 'ok' : lv === 'warn' || lv === 'low' || lv === 'high' ? 'warn' : 'neutral',
    desc: rangeText ? `合理区间 ${rangeText}` : '供能比'
  }
}

function trendMicroView(micro) {
  if (!micro || typeof micro !== 'object' || Array.isArray(micro)) return {}
  const out = {}
  Object.keys(micro).forEach((k) => {
    out[k] = numOrNull(micro[k])
  })
  return out
}

function trendDayView(day, i) {
  const d = day || {}
  const date = str(pick(d, 'date'), '')
  const statusZh = str(pick(d, 'status'), '参考提示')
  return {
    date,
    label: str(pick(d, 'label'), date.slice(5) || `第${i + 1}天`),
    calories: numOrNull(pick(d, 'calories')),
    protein_g: numOrNull(pick(d, 'protein_g')),
    fat_g: numOrNull(pick(d, 'fat_g')),
    carb_g: numOrNull(pick(d, 'carb_g')),
    fiber_g: numOrNull(pick(d, 'fiber_g')),
    oil_g: numOrNull(pick(d, 'oil_g')),
    salt_g: numOrNull(pick(d, 'salt_g')),
    micro: trendMicroView(pick(d, 'micro')),
    meal_count: numOrNull(pick(d, 'meal_count')),
    known_meal_count: numOrNull(pick(d, 'known_meal_count')),
    status: ['ok', 'over', 'low'].includes(statusZh) ? statusZh : 'neutral',
    status_zh: statusZh,
    show_date: true
  }
}

function normalizeDailyTrend(list) {
  return arr(list).map(trendDayView)
}

function achievementView(achievement) {
  if (!achievement || typeof achievement !== 'object' || Array.isArray(achievement)) return null
  const macro = achievement.macro && typeof achievement.macro === 'object' ? achievement.macro : {}
  const micro = achievement.micro && typeof achievement.micro === 'object' ? achievement.micro : {}
  return {
    micro_overall_pct: numOrNull(pick(achievement, 'micro_overall_pct')),
    macro,
    micro
  }
}

function composeSummary(daySpan, mealCount, energy, segments) {
  const parts = []
  if (daySpan != null) parts.push(`覆盖 ${daySpan} 天`)
  if (energy != null) parts.push(`日均 ${energy} kcal`)
  if (mealCount != null) parts.push(`共 ${mealCount} 餐`)
  const pcts = segments
    .filter((s) => s.percent !== null && s.percent !== undefined)
    .map((s) => `${s.name} ${s.percent}%`)
  if (pcts.length) parts.push(pcts.join(' / '))
  return parts.join(' · ')
}

export function normalizeReport(report) {
  const r = report || {}
  const macro = r.macro_summary || {}
  const microMap = r.key_micro_summary || {}
  const completeness = r.completeness || {}
  const summary = r.summary || {}
  const trendSource = arr(pick(summary, 'daily_trend')).length
    ? pick(summary, 'daily_trend')
    : pick(r, 'daily_trend')
  const reportType = str(pick(r, 'report_type'), 'plan')
  const start = str(pick(r, 'period_start'), '')
  const end = str(pick(r, 'period_end'), '')
  const daySpan =
    start && end
      ? Math.max(1, Math.round((new Date(end) - new Date(start)) / 86400000) + 1)
      : null
  const achievement = achievementView(pick(summary, 'achievement'))
  const macroAchieve = (achievement && achievement.macro) || {}
  const microAchieve = (achievement && achievement.micro) || {}
  const mealCount = numOrNull(pick(completeness, 'meal_count'))
  const energy = numOrNull(pick(macro, 'energy_kcal'))
  const planStats = pick(summary, 'plan_stats') || {}

  const macroCell = (key) => macroAchieve[key] || {}
  const segments = [
    macroSegment(
      '蛋白质', pick(macro, 'protein_pct'), 'protein',
      macroCell('protein_pct').level, macroCell('protein_pct').range
    ),
    macroSegment(
      '碳水', pick(macro, 'carb_pct'), 'carb',
      macroCell('carb_pct').level, macroCell('carb_pct').range
    ),
    macroSegment(
      '脂肪', pick(macro, 'fat_pct'), 'fat',
      macroCell('fat_pct').level, macroCell('fat_pct').range
    )
  ]

  const microItems = MICRO_KEYS.map((k) => {
    const it = microView(microMap[k], k)
    if (!it.name) return null
    const a = microAchieve[k] || {}
    it.achieved_days = numOrNull(a.achieved_days)
    it.valid_days = numOrNull(a.valid_days)
    it.achieved_pct = numOrNull(a.achieved_pct)
    return it
  }).filter(Boolean)

  return {
    report_id: str(pick(r, 'nutrition_report_id'), ''),
    meal_plan_id: str(pick(r, 'meal_plan_id'), ''),
    scope: reportType,
    report_type: reportType,
    headline:
      reportType === 'plan'
        ? `方案营养复盘（${daySpan ?? '—'} 天）`
        : reportType === 'week'
          ? '周膳食报告'
          : reportType === 'month'
            ? '月膳食报告'
            : reportType === 'custom'
              ? '自定义膳食报告'
              : '膳食报告',
    meta: {
      range_start: start,
      range_end: end,
      range_text: start && end ? `${start} ~ ${end}` : '—',
      generated_at: str(pick(r, 'generated_at'), ''),
      window_days: numOrNull(pick(r, 'window_days')),
      valid_days: daySpan,
      total_meals: mealCount,
      target_kcal: energy
    },
    summary_text: composeSummary(daySpan, mealCount, energy, segments),
    macro: {
      center_value: fmtNum(energy),
      center_label: 'kcal',
      segments
    },
    extra_metrics: [
      { key: 'oil', name: '烹调油', value: pick(macro, 'oil_g'), unit: 'g' },
      { key: 'salt', name: '食盐', value: pick(macro, 'salt_g'), unit: 'g' },
      { key: 'fiber', name: '膳食纤维', value: pick(macro, 'fiber_g'), unit: 'g' }
    ],
    micro: {
      title: '关键微量（覆盖度）',
      items: microItems,
      overall_pct: achievement ? numOrNull(achievement.micro_overall_pct) : null
    },
    completeness: {
      meal_count: mealCount,
      known_meal_count: numOrNull(pick(completeness, 'known_meal_count')),
      missing_meal_count: numOrNull(pick(completeness, 'missing_meal_count'))
    },
    reference_hints: arr(pick(summary, 'reference_hints')),
    data_quality_notes: arr(pick(summary, 'data_quality_notes')),
    plan_stats: {
      total_plans: numOrNull(pick(planStats, 'total_plans')),
      executed_plans: numOrNull(pick(planStats, 'executed_plans'))
    },
    achievement,
    sources: arr(pick(r, 'sources')),
    insights: arr(pick(summary, 'insights')),
    daily_trend: normalizeDailyTrend(trendSource),
    expanded: false
  }
}

/* ---------- artifact 分发 ---------- */

export function normalizeArtifact(type, payload) {
  if (type === 'meal_card') return normalizeMealCard(payload)
  if (type === 'current_plan') return normalizeCurrentPlan(payload)
  if (type === 'shopping_list') {
    return {
      type: 'shopping_list',
      raw_id: str(pick(payload, 'shopping_list_id'), ''),
      meal_plan_id: str(pick(payload, 'meal_plan_id'), ''),
      total_items: numOrNull(pick(payload, 'total_items')),
      generated_at: str(pick(payload, 'generated_at'), ''),
      groups: normalizeGroups(pick(payload, 'groups'))
    }
  }
  if (type === 'nutrition_report') return { type: 'nutrition_report', ...normalizeReport(payload) }
  if (type === 'quick_actions') {
    return {
      type: 'quick_actions',
      actions: Array.isArray(payload.actions)
        ? payload.actions.map((a) => ({ label: str(pick(a, 'label'), ''), phrase: str(pick(a, 'phrase'), '') }))
        : []
    }
  }
  return { type: 'unknown', raw_type: str(type, ''), payload }
}
