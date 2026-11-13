/**
 * schema 归一化：后端字段可能用 snake_case 或 camelCase，
 * 且允许缺字段。这里把「可能缺」的对象补成渲染器能直接用的形状，
 * 缺字段时给默认值，不抛错。
 */

export function pick(obj, ...keys) {
  if (!obj || typeof obj !== 'object') return undefined
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k]
  }
  return undefined
}

export function num(v, fallback = 0) {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

export function arr(v) {
  return Array.isArray(v) ? v : []
}

export function str(v, fallback = '') {
  return typeof v === 'string' ? v : v == null ? fallback : String(v)
}

const TYPE_ALIASES = {
  meal_card: 'meal_card',
  mealcard: 'meal_card',
  recipe_card: 'meal_card',
  meal_plan: 'meal_plan',
  mealplan: 'meal_plan',
  week_plan: 'meal_plan',
  plan_detail: 'meal_plan',
  nutrition: 'nutrition',
  nutrition_report: 'nutrition',
  recipe_detail: 'recipe_detail',
  recipe: 'recipe_detail',
  shopping_list: 'shopping_list',
  shopping: 'shopping_list',
  grocery: 'shopping_list',
  report: 'report',
  meal_report: 'report',
  sources: 'sources',
  source: 'sources',
  medical_hint: 'medical_hint',
  health_hint: 'medical_hint',
  anchor: 'anchor',
  jump: 'anchor',
  text: 'text'
}

function inferType(block) {
  if (!block || typeof block !== 'object') return 'unknown'
  if (Array.isArray(block.items) && block.items.some((i) => i && (i.url || i.title))) return 'sources'
  if (block.daily_trend || block.dailyTrend) return 'report'
  if (block.headline && block.meta) return 'report'
  if (Array.isArray(block.groups)) return 'shopping_list'
  if (block.macro && block.micro) return 'nutrition'
  if (Array.isArray(block.days)) return block.plan_id ? 'meal_plan' : 'meal_plan'
  if (Array.isArray(block.slots) || Array.isArray(block.meals)) return 'meal_card'
  if (block.level && (block.text || block.content)) return 'medical_hint'
  if (Array.isArray(block.anchors) || Array.isArray(block.actions)) return 'anchor'
  return 'unknown'
}

/**
 * meta → blocks[]
 * 兼容三种形态：
 *  1) { blocks: [ ... ] }
 *  2) [ ... ]
 *  3) { meal_card: {...}, nutrition: {...} }（按 key 展开）
 */
export function normalizeBlocks(meta) {
  if (!meta) return []
  let list = []
  if (Array.isArray(meta)) list = meta
  else if (Array.isArray(meta.blocks)) list = meta.blocks
  else {
    const expandable = Object.keys(meta).filter((k) => k !== 'blocks' && typeof meta[k] === 'object' && meta[k] !== null)
    if (expandable.length && expandable.some((k) => TYPE_ALIASES[k.toLowerCase()])) {
      list = expandable.map((k) => ({ type: TYPE_ALIASES[k.toLowerCase()] || k, ...meta[k] }))
    } else {
      list = [meta]
    }
  }

  return list
    .filter((b) => b && typeof b === 'object')
    .map((b, i) => {
      const rawType = str(b.type, '')
      const type = TYPE_ALIASES[rawType.toLowerCase()] || inferType(b)
      return { ...b, type, __key: str(b.card_id || b.plan_id || b.report_id, `b${i}`) + '-' + i }
    })
}

export function normalizeSlot(slot) {
  const s = slot || {}
  const dishes = arr(pick(s, 'dishes', 'dish_list', 'items')).map((d) => ({
    name: str(pick(d, 'name', 'dish', 'title'), '未命名菜品'),
    amount: str(pick(d, 'amount', 'portion', 'quantity'), ''),
    kcal: num(pick(d, 'kcal', 'calories', 'energy'), 0),
    tip: str(pick(d, 'tip', 'note', 'tips'), ''),
    steps: arr(pick(d, 'steps', 'procedures')),
    is_staple: Boolean(pick(d, 'is_staple', 'isStaple'))
  }))

  const candidates = arr(s.candidates).map((c, i) => ({
    candidate_id: str(pick(c, 'candidate_id', 'id'), `c${i}`),
    name: str(pick(c, 'name', 'title'), `方案 ${i + 1}`),
    kcal: num(pick(c, 'kcal', 'calories'), 0),
    desc: str(pick(c, 'desc', 'description'), ''),
    dishes: arr(c.dishes).map((d) => ({
      name: str(pick(d, 'name'), ''),
      amount: str(pick(d, 'amount'), ''),
      kcal: num(pick(d, 'kcal'), 0),
      tip: str(pick(d, 'tip'), '')
    }))
  }))

  const micro = arr(pick(s, 'micro', 'micro_coverage', 'microCoverage')).map((m) => normalizeMicroItem(m))

  return {
    slot_id: str(pick(s, 'slot_id', 'id'), ''),
    meal_type: str(pick(s, 'meal_type', 'type'), 'lunch'),
    label: str(pick(s, 'label', 'name', 'meal_label'), ''),
    time: str(pick(s, 'time'), ''),
    kcal: num(pick(s, 'kcal', 'calories'), 0),
    oil_g: pick(s, 'oil_g', 'oilG'),
    salt_g: pick(s, 'salt_g', 'saltG'),
    dishes,
    dish_text: str(pick(s, 'dish_text', 'dishText'), dishes.map((d) => d.name).join(' + ')),
    dish_count: num(pick(s, 'dish_count'), dishes.length),
    candidates,
    selected_candidate_id: str(pick(s, 'selected_candidate_id', 'selectedCandidateId'), ''),
    micro
  }
}

export function normalizeMicroItem(m) {
  const item = m || {}
  const percent = num(pick(item, 'ring_percent', 'percent', 'value_pct'), 0)
  const statusRaw = str(pick(item, 'status', 'level'), 'ok')
  const status = ['ok', 'warn', 'danger'].includes(statusRaw) ? statusRaw : percent >= 80 ? 'ok' : percent >= 50 ? 'warn' : 'danger'
  return {
    name: str(pick(item, 'name'), ''),
    value: str(pick(item, 'value', 'display'), `${percent}%`),
    percent: Math.min(100, Math.max(0, percent)),
    status,
    note: str(pick(item, 'note', 'caption'), '')
  }
}

export function normalizeMacro(macro) {
  const m = macro || {}
  const segments = arr(pick(m, 'segments', 'items')).map((s) => {
    const seg = s || {}
    return {
      name: str(pick(seg, 'name', 'label'), ''),
      percent: num(pick(seg, 'percent', 'value'), 0),
      color: str(pick(seg, 'color', 'key'), ''),
      tag: str(pick(seg, 'tag', 'label_tag'), ''),
      tag_level: str(pick(seg, 'tag_level', 'tagLevel', 'level'), 'ok'),
      desc: str(pick(seg, 'desc', 'description'), '')
    }
  })
  return {
    center_value: str(pick(m, 'center_value', 'centerValue', 'value'), ''),
    center_label: str(pick(m, 'center_label', 'centerLabel', 'label'), ''),
    segments
  }
}

export function normalizeNutrition(block) {
  const b = block || {}
  return {
    scope: str(pick(b, 'scope'), 'day'),
    macro: normalizeMacro(pick(b, 'macro', 'macro_donut', 'macroDonut')),
    micro: {
      title: str(pick(pick(b, 'micro', 'micro_grid', 'microGrid'), 'title'), '关键微量元素覆盖'),
      items: arr(pick(pick(b, 'micro', 'micro_grid', 'microGrid'), 'items')).map(normalizeMicroItem)
    },
    insights: arr(pick(b, 'insights', 'tips')),
    coverage: pick(b, 'coverage') || null
  }
}

export function normalizeReport(report) {
  const r = report || {}
  const meta = r.meta || {}
  return {
    report_id: str(pick(r, 'report_id', 'id'), ''),
    scope: str(pick(r, 'scope'), 'week'),
    headline: str(pick(r, 'headline', 'title'), '膳食报告'),
    meta: {
      range_start: str(pick(meta, 'range_start', 'start'), ''),
      range_end: str(pick(meta, 'range_end', 'end'), ''),
      generated_at: str(pick(meta, 'generated_at', 'generatedAt'), ''),
      valid_days: num(pick(meta, 'valid_days', 'validDays'), 0),
      total_meals: num(pick(meta, 'total_meals', 'totalMeals'), 0),
      target_kcal: num(pick(meta, 'target_kcal', 'targetKcal'), 0)
    },
    summary_text: str(pick(r, 'summary_text', 'summary'), ''),
    macro: normalizeMacro(pick(r, 'macro', 'macro_donut')),
    micro: {
      title: str(pick(r.micro, 'title'), '关键微量达标率'),
      items: arr(pick(r.micro, 'items')).map(normalizeMicroItem)
    },
    daily_trend: arr(pick(r, 'daily_trend', 'dailyTrend')).map((d) => ({
      date: str(pick(d, 'date', 'label'), ''),
      calories: num(pick(d, 'calories', 'kcal'), 0),
      show_date: Boolean(pick(d, 'show_date', 'showDate')),
      status: str(pick(d, 'status'), 'ok')
    })),
    insights: arr(pick(r, 'insights', 'analysis')),
    expanded: Boolean(pick(r, 'expanded'))
  }
}

export function normalizeGroups(groups) {
  return arr(groups).map((g, gi) => ({
    group_id: str(pick(g, 'group_id', 'id'), `g${gi}`),
    day: pick(g, 'day') || null,
    day_date: pick(g, 'day_date', 'dayDate') || null,
    category: str(pick(g, 'category', 'name'), '其他'),
    items: arr(g.items).map((it, ii) => ({
      item_id: str(pick(it, 'item_id', 'id'), `it${gi}${ii}`),
      name: str(pick(it, 'name'), ''),
      amount: str(pick(it, 'amount', 'quantity'), ''),
      is_staple: Boolean(pick(it, 'is_staple', 'isStaple')),
      checked: Boolean(pick(it, 'checked'))
    }))
  }))
}

export function normalizePlan(plan) {
  const p = plan || {}
  const days = arr(pick(p, 'days')).map((d) => ({
    date: str(pick(d, 'date', 'label'), ''),
    weekday: str(pick(d, 'weekday'), ''),
    is_today: Boolean(pick(d, 'is_today', 'isToday')),
    kcal: num(pick(d, 'kcal', 'calories'), 0),
    slots: arr(pick(d, 'slots', 'meals')).map(normalizeSlot)
  }))
  return {
    plan_id: str(pick(p, 'plan_id', 'id'), ''),
    plan_type: str(pick(p, 'plan_type', 'type'), 'day'),
    status: str(pick(p, 'status'), 'draft'),
    title: str(pick(p, 'title'), ''),
    subtitle: str(pick(p, 'subtitle', 'sub'), ''),
    range_text: str(pick(p, 'range_text', 'range'), ''),
    goal_text: str(pick(p, 'goal_text', 'goalText', 'target_text'), ''),
    target_kcal: num(pick(p, 'goal_energy_kcal', 'target_kcal', 'targetKcal'), 0),
    total_kcal: num(pick(p, 'total_kcal'), days[0] ? days[0].kcal : 0),
    days,
    nutrition: p.nutrition || null,
    sources: arr(pick(p, 'sources')),
    reason_points: arr(pick(p, 'reason_points', 'reasonPoints')),
    updated_at: str(pick(p, 'updated_at', 'updatedAt'), ''),
    executed: Boolean(pick(p, 'executed'))
  }
}
