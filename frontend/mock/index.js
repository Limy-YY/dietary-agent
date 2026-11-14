/**
 * Mock 后端（v1.2）：SSE 四类事件 + REST 契约路由。
 * 事件：message{type,content} / artifact{type,payload} / clarify / error / done
 * 响应：{ code, message, data }，data 直接是对象；列表为 {total,page,page_size,items}
 */
import {
  state,
  getProfile,
  saveProfile,
  createPlan,
  currentPlanRecord,
  getCurrentPlanPayload,
  getPlanPayload,
  listPlans,
  swapCandidate,
  fixPlan,
  getShoppingListPayload,
  reportForPlan,
  getReportPayload,
  findRecord,
  GOAL_NAMES,
  CONDITION_IDS,
  getConditionCatalog,
  resetState
} from './store.js'

const ok = (data) => ({ code: 0, message: 'ok', data })
const fail = (code, message) => ({ code, message, data: null })

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = ''
    req.on('data', (c) => {
      raw += c
    })
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {})
      } catch (e) {
        reject(e)
      }
    })
    req.on('error', reject)
  })
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

function isoDate(offset = 0) {
  const d = new Date()
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate() + offset)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

/* ---------------- 意图路由 ---------------- */

function mealLabelOf(message) {
  if (message.includes('早')) return '早'
  if (message.includes('晚')) return '晚'
  return '午'
}

function findSlotByMeal(record, meal) {
  if (!record) return null
  return record.card.slots.find((s) => s.meal_type === meal) || record.card.slots[0] || null
}

function candidateName(c) {
  return (c.dishes || []).map((d) => d.name).join(' + ') || `候选 ${c.rank}`
}

function planIntro(card) {
  const goal = GOAL_NAMES[card.goal_code] || '均衡'
  if (card.plan_type === '周') {
    return `收到！按你的${goal}档案排了接下来七天（${card.start_date} ~ ${card.end_date}）的三餐，每个餐位 2~3 个候选，食材尽量不重复：`
  }
  if (card.plan_type === '餐') {
    return '这一餐给你挑了三个方向，热量都在参考区间，点一个候选就能确认：'
  }
  if (card.plan_type === '多日') {
    return `按你的${goal}档案排了 ${card.start_date} ~ ${card.end_date} 的方案，按天拆开，候选备好了：`
  }
  return `收到！已结合你的${goal}档案，为你生成了今天的方案，候选都在里面：`
}

function generate(kind) {
  if (kind === 'week') {
    return createPlan({ start_date: isoDate(0), end_date: isoDate(6), plan_type: '周' })
  }
  if (kind === 'meal') {
    return createPlan({ start_date: isoDate(0), end_date: isoDate(0), plan_type: '餐' })
  }
  if (kind === 'multi') {
    return createPlan({ start_date: isoDate(0), end_date: isoDate(2), plan_type: '多日' })
  }
  return createPlan({ start_date: isoDate(0), end_date: isoDate(0), plan_type: '日' })
}

function missingProfileFields() {
  const p = state.profile
  const miss = []
  if (!p.gender) miss.push('gender')
  if (!p.age) miss.push('age')
  if (!p.height_cm) miss.push('height_cm')
  if (!p.weight_kg) miss.push('weight_kg')
  if (!p.goal_code) miss.push('goal_code')
  return miss
}

function routeIntent(rawMessage) {
  const message = String(rawMessage || '').trim()
  const has = (re) => re.test(message)
  const artifacts = []

  /* 1. 选候选 */
  if (has(/选用|就选|选第/)) {
    const record = currentPlanRecord()
    if (!record) return { text: '还没有可以选候选的方案，先让我配一份？', artifacts: [] }
    if (record.card.status === 'fixed') {
      return { text: '这份方案已经固定，候选不能再改。要调整的话，我们重新配一份。', artifacts: [] }
    }
    const slot = findSlotByMeal(record, mealLabelOf(message))
    const candidate = slot.candidates.find((c) => message.includes(candidateName(c))) || slot.candidates[0]
    const res = swapCandidate({
      meal_plan_id: record.id,
      meal_slot_id: slot.meal_slot_id,
      candidate_id: candidate.candidate_id
    })
    if (res.error) return { text: res.error.message, artifacts: [] }
    artifacts.push({ type: 'meal_card', payload: getPlanPayload(record.id) })
    return {
      text: `${slot.meal_type}餐改成「${candidateName(res.candidate)}」，约 ${res.candidate.macro_estimate.kcal == null ? '—' : res.candidate.macro_estimate.kcal} kcal。方案仍是待确认，确认后才会写进右侧。`,
      artifacts
    }
  }

  /* 2. 换候选 */
  if (has(/换一换|更换|换一餐|换个|换掉/)) {
    const record = currentPlanRecord()
    if (!record) {
      return { text: '还没有可以先换的方案。要不要我先生成今天的搭配？', artifacts: [] }
    }
    if (record.card.status === 'fixed') {
      return { text: '这份方案已经固定，改不了候选。要调整的话，我们重新配一份？', artifacts: [] }
    }
    const slot = findSlotByMeal(record, mealLabelOf(message))
    const res = swapCandidate({ meal_plan_id: record.id, meal_slot_id: slot.meal_slot_id })
    if (res.error) {
      return { text: res.error.message, artifacts: [] }
    }
    artifacts.push({ type: 'meal_card', payload: getPlanPayload(record.id) })
    const kcal = res.candidate.macro_estimate.kcal
    return {
      text: `换好了。${slot.meal_type}餐换成「${candidateName(res.candidate)}」，这一餐约 ${kcal == null ? '—' : kcal} kcal（估算值），方案还是未固定状态，确认后才会写进右侧。`,
      artifacts
    }
  }

  /* 2. 确认 / 固定 */
  if (has(/确认|固定|就这个|可以了|没问题/)) {
    const record = currentPlanRecord()
    if (!record) {
      return { text: '现在还没有待确认的方案。我可以先按你的档案排今天的三餐，也可以排一周。', artifacts: [] }
    }
    if (record.card.status === 'fixed') {
      const shop = getShoppingListPayload(record.id)
      return {
        text: '这份方案已经固定过了。右侧「当前规划」和「食材清单」里都能回看。',
        artifacts: [
          { type: 'meal_card', payload: record.card },
          ...(shop.error ? [] : [{ type: 'shopping_list', payload: shop }])
        ]
      }
    }
    const fixed = fixPlan({ meal_plan_id: record.id })
    if (fixed.error) {
      return { text: fixed.error.message, artifacts: [] }
    }
    const shop = getShoppingListPayload(record.id)
    const total = shop.total_items || 0
    return {
      text: `已固定，方案生效。右侧「当前规划」和「食材清单」同步完成，清单共 ${total} 项，按类别分好了（数量为估算值）。`,
      artifacts: [
        { type: 'meal_card', payload: fixed },
        ...(shop.error ? [] : [{ type: 'shopping_list', payload: shop }])
      ]
    }
  }

  /* 3. 膳食报告 */
  if (has(/报告|复盘/)) {
    const record = currentPlanRecord()
    if (!record) {
      return { text: '还没有可复盘的方案。先让我给你配一份，再生成报告？', artifacts: [] }
    }
    const report = reportForPlan(record.id)
    if (report.error) return { text: report.error.message, artifacts: [] }
    const completeness = report.completeness || {}
    return {
      text: `已按方案生成 ${record.card.start_date} ~ ${record.card.end_date} 的膳食报告，覆盖 ${completeness.meal_count || 0} 餐。点「展开查看」看完整分析，右侧「膳食报告」里也能回看；月/周口径暂只支持方案级报告。`,
      artifacts: [
        { type: 'nutrition_report', payload: report },
        { type: 'meal_card', payload: record.card }
      ]
    }
  }

  /* 4. 食材清单 */
  if (has(/食材|清单|买菜|采购/)) {
    const record = currentPlanRecord()
    if (!record) {
      return { text: '还没有方案，清单自然也没有。先让我按你的档案配一份？', artifacts: [] }
    }
    const shop = getShoppingListPayload(record.id)
    if (shop.error) {
      return { text: '方案还没固定，清单暂时是空的。确认方案后我就按类别拆好食材。', artifacts: [] }
    }
    return {
      text: `清单已经整理好，共 ${shop.total_items} 项，按类别分好了。数量是估算值，按实际采购调整。`,
      artifacts: [{ type: 'shopping_list', payload: shop }]
    }
  }

  /* 5. 生成方案 */
  if (has(/一周|七天|7天|整周/)) {
    const res = generate('week')
    if (res.error) return { text: res.error.message, artifacts: [] }
    artifacts.push({ type: 'meal_card', payload: res.plan })
    return { text: planIntro(res.plan), artifacts }
  }
  if (has(/三天|3天|这三天|多日/)) {
    const res = generate('multi')
    if (res.error) return { text: res.error.message, artifacts: [] }
    artifacts.push({ type: 'meal_card', payload: res.plan })
    return { text: planIntro(res.plan), artifacts }
  }
  if (has(/一餐|推荐|午餐|晚餐|早餐/) && !has(/三餐|一日/)) {
    const res = generate('meal')
    if (res.error) return { text: res.error.message, artifacts: [] }
    artifacts.push({ type: 'meal_card', payload: res.plan })
    return { text: planIntro(res.plan), artifacts }
  }
  if (has(/三餐|一日|今天|明天|吃什么|搭配/)) {
    const res = generate('day')
    if (res.error) return { text: res.error.message, artifacts: [] }
    artifacts.push({ type: 'meal_card', payload: res.plan })
    return { text: planIntro(res.plan), artifacts }
  }

  /* 6. 微量 / 症状咨询（纯文本 + 就医提示） */
  if (has(/微量|营养|缺什么|乏力|掉发|头晕|抽筋|便秘/)) {
    return {
      text: '先说结论：单看一份食谱判断不了你身上的具体症状，但可以从近七天的摄入趋势看缺口。你的记录里维生素 C 和钙的达标天数偏少，先按方案把这两项补上，观察 2～4 周。如果症状持续或加重，建议直接就医，别靠调整饮食硬扛。',
      artifacts: []
    }
  }

  /* 7. 兜底 */
  return {
    text: '这个我暂时答不好。可以让我按档案排今天的三餐、换一餐的候选、或者生成一份膳食报告，这几件事我做得稳一些。',
    artifacts: []
  }
}

/* ---------------- SSE ---------------- */

async function streamChat(req, res, body) {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no'
  })

  const send = (event, data) => {
    res.write(`event: ${event}\n`)
    res.write(`data: ${JSON.stringify(data)}\n\n`)
  }

  const conversationId = body.conversation_id || `conv_${Date.now()}`
  const text = String(body.message || '')
  const missing = missingProfileFields()
  const wantsPlan = /三餐|一日|今天|明天|吃什么|搭配|一周|七天|整周|一餐|推荐|午餐|晚餐|早餐/.test(text)

  // 信息不足必须先追问，符合「needs_clarification 必须追问」
  if (wantsPlan && missing.length) {
    send('clarify', {
      question: '配餐前还需要你补充几项档案信息：' + missing.join('、'),
      missing_fields: missing
    })
    send('done', { conversation_id: conversationId, meal_plan_id: null, finish_reason: 'clarify' })
    res.end()
    return
  }

  const result = routeIntent(text)
  const chunks = []
  let i = 0
  while (i < result.text.length) {
    const step = 3 + Math.floor(Math.random() * 5)
    chunks.push(result.text.slice(i, i + step))
    i += step
  }
  for (const chunk of chunks) {
    send('message', { type: 'text', content: chunk })
    await sleep(24)
  }

  let mealPlanId = null
  for (const art of result.artifacts || []) {
    await sleep(50)
    send('artifact', { type: art.type, payload: art.payload })
    if (art.type === 'meal_card' && art.payload && art.payload.meal_plan_id != null) {
      mealPlanId = art.payload.meal_plan_id
    }
  }

  send('done', {
    conversation_id: conversationId,
    meal_plan_id: mealPlanId,
    finish_reason: 'stop'
  })
  res.end()
}

/* ---------------- HTTP ---------------- */

async function handle(req, res, pathname, searchParams) {
  const token = req.headers['authorization']
  const json = (payload, status = 200) => {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify(payload))
  }

  /* 仅 mock：联调前清状态（不在契约内） */
  if (pathname === '/__reset' && req.method === 'POST') {
    json(ok(resetState()))
    return
  }

  if (!token) {
    json(fail(1002, '登录状态已失效，请重新登录'))
    return
  }

  /* 对话 */
  if (pathname === '/agent/chat' && req.method === 'POST') {
    const body = await readBody(req)
    if (!body.message || !String(body.message).trim()) {
      json(fail(1001, 'message 不能为空'))
      return
    }
    await streamChat(req, res, body)
    return
  }

  /* 病种目录 */
  if (pathname === '/conditions/catalog' && req.method === 'GET') {
    await sleep(30)
    json(ok(getConditionCatalog()))
    return
  }

  /* 档案 */
  if (pathname === '/profile' && req.method === 'GET') {
    await sleep(60)
    json(ok(getProfile()))
    return
  }
  if (pathname === '/profile' && req.method === 'PUT') {
    const body = await readBody(req)
    const gender = body.gender
    if (gender !== undefined && !['男', '女'].includes(gender)) {
      json(fail(1001, 'gender 只能取 男/女'))
      return
    }
    if (body.age !== undefined && !(Number(body.age) >= 10 && Number(body.age) <= 100)) {
      json(fail(1001, 'age 需在 10～100 岁之间'))
      return
    }
    if (body.height_cm !== undefined && !(Number(body.height_cm) >= 120 && Number(body.height_cm) <= 220)) {
      json(fail(1001, 'height_cm 需在 120～220 cm 之间'))
      return
    }
    if (body.weight_kg !== undefined && !(Number(body.weight_kg) >= 30 && Number(body.weight_kg) <= 200)) {
      json(fail(1001, 'weight_kg 需在 30～200 kg 之间'))
      return
    }
    if (body.goal_code !== undefined && !Object.keys(GOAL_NAMES).includes(body.goal_code)) {
      json(fail(1001, 'goal_code 不在 goal_structure_map 值域内'))
      return
    }
    if (body.conditions !== undefined) {
      const bad = CONDITION_IDS.some((id) => {
        const raw = body.conditions[id]
        if (!raw) return false
        const st = typeof raw === 'string' ? raw : raw.status
        return st !== undefined && !['confirmed', 'suspected', 'unknown'].includes(st)
      })
      if (bad) {
        json(fail(1001, 'conditions.status 只能是 confirmed/suspected/unknown'))
        return
      }
    }
    await sleep(100)
    json(ok(saveProfile(body)))
    return
  }

  /* 方案 */
  if (pathname === '/meal-plan/current' && req.method === 'GET') {
    await sleep(60)
    json(ok(getCurrentPlanPayload()))
    return
  }
  if (pathname === '/meal-plan/list' && req.method === 'GET') {
    await sleep(60)
    json(ok(listPlans({
      page: searchParams.get('page') || 1,
      page_size: searchParams.get('page_size') || 20,
      status: searchParams.get('status') || undefined
    })))
    return
  }
  if (pathname === '/meal-plan/week/generate' && req.method === 'POST') {
    const body = await readBody(req)
    if (!body.start_date || !body.end_date) {
      json(fail(1001, 'start_date / end_date 必填'))
      return
    }
    const resPlan = createPlan(body)
    if (resPlan.error) {
      json(fail(resPlan.error.code, resPlan.error.message))
      return
    }
    await sleep(60)
    json(ok(resPlan.plan))
    return
  }
  if (pathname === '/meal-plan/candidate/swap' && req.method === 'POST') {
    const body = await readBody(req)
    if (body.meal_plan_id == null || body.meal_slot_id == null) {
      json(fail(1001, 'meal_plan_id / meal_slot_id 必填'))
      return
    }
    const result = swapCandidate(body)
    if (result.error) {
      json(fail(result.error.code, result.error.message))
      return
    }
    json(ok(result))
    return
  }
  if (pathname === '/meal-plan/week/fix' && req.method === 'POST') {
    const body = await readBody(req)
    if (body.meal_plan_id == null) {
      json(fail(1001, 'meal_plan_id 必填'))
      return
    }
    const result = fixPlan(body)
    if (result.error) {
      json(fail(result.error.code, result.error.message))
      return
    }
    json(ok(result))
    return
  }

  const planMatch = pathname.match(/^\/meal-plan\/([^/]+)$/)
  if (planMatch && req.method === 'GET' && !['current', 'list'].includes(planMatch[1])) {
    await sleep(60)
    const plan = getPlanPayload(decodeURIComponent(planMatch[1]))
    if (!plan) {
      json(fail(1004, '方案不存在'))
      return
    }
    json(ok(plan))
    return
  }

  /* 食材清单 */
  if (pathname === '/shopping-list' && req.method === 'GET') {
    const planId = searchParams.get('meal_plan_id')
    if (!planId) {
      json(fail(1001, 'meal_plan_id 必填'))
      return
    }
    const list = getShoppingListPayload(planId)
    if (list.error) {
      json(fail(list.error.code, list.error.message))
      return
    }
    json(ok(list))
    return
  }

  /* 营养分析与报告 */
  if (pathname === '/nutrition/analysis' && req.method === 'POST') {
    const body = await readBody(req)
    if (body.meal_plan_id == null) {
      json(fail(1001, 'meal_plan_id 必填'))
      return
    }
    const windowDays = Number(body.window_days) || 7
    if (windowDays < 3 || windowDays > 30) {
      json(fail(1001, 'window_days 需在 3～30 之间'))
      return
    }
    const report = reportForPlan(body.meal_plan_id, { window_days: windowDays })
    if (report.error) {
      json(fail(report.error.code, report.error.message))
      return
    }
    json(ok(report))
    return
  }
  if (pathname === '/nutrition/report' && req.method === 'GET') {
    const planId = searchParams.get('meal_plan_id')
    if (!planId) {
      json(fail(1001, 'meal_plan_id 必填'))
      return
    }
    const report = getReportPayload(planId)
    if (report.error) {
      json(fail(report.error.code, report.error.message))
      return
    }
    json(ok(report))
    return
  }

  if (pathname === '/health') {
    json(ok({ status: 'ok', mock: true, contract: 'v1.2' }))
    return
  }

  json(fail(2404, `Mock 未实现的接口：${req.method} ${pathname}`), 404)
}

export default function mockPlugin() {
  return {
    name: 'shanzhuo-mock-api',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api', (req, res, next) => {
        const url = new URL(req.url || '/', 'http://127.0.0.1')
        handle(req, res, url.pathname, url.searchParams).catch((e) => {
          if (!res.headersSent) {
            res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' })
            res.end(JSON.stringify(fail(2500, `Mock 内部错误：${e.message}`)))
          } else {
            res.end()
          }
        })
      })
      server.middlewares.use((req, res, next) => next())
    }
  }
}
