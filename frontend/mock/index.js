import { state, getProfile, saveProfile, getCurrentPlan, getPlanById, listPlans, createPlan, confirmPlan, swapCandidate, chooseCandidate, getShoppingList, getNutritionReport, generateReport, mealCardBlock, mealPlanBlock, nutritionBlock, recipeBlock, sourcesBlock, anchorBlock, shoppingBlock, reportBlock } from './store.js'

const ok = (data) => ({ code: 0, message: 'success', data })
const fail = (code, message, data = null) => ({ code, message, data })
const empty = (message) => ({ code: 1004, message, data: null })

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

/* ================= 意图路由（模拟 Agent 编排结果） ================= */

function goalText() {
  const g = state.profile.extras.goals && state.profile.extras.goals.length ? state.profile.extras.goals : [state.profile.goal]
  return g.join('、')
}

function planIntro(plan) {
  if (plan.plan_type === 'week') {
    return `收到！按你的${goalText()}档案排了接下来七天（${plan.range_text}）的三餐，食材尽量不重复：`
  }
  if (plan.plan_type === 'meal') {
    return '午餐给你挑了三个方向，热量都在 620～680 kcal，点一个就能确认：'
  }
  return `收到！已结合你的${goalText()}档案，为你生成了今天的方案：`
}

function routeIntent(rawMessage) {
  const message = String(rawMessage || '').trim()
  const has = (re) => re.test(message)

  /* 1. 换候选 */
  if (has(/换一换|更换|换一餐|换个|换掉/)) {
    const label = ['早餐', '午餐', '晚餐'].find((l) => message.includes(l)) || '午餐'
    const res = swapCandidate(label)
    if (!res) {
      return {
        text: '还没有可以先换的方案。要不要我先生成今天的搭配？',
        blocks: [anchorBlock([{ panel: 'current_plan', label: '查看当前规划' }])]
      }
    }
    const plan = getCurrentPlan()
    const dishText = res.candidate.name.split('·').slice(1).join('·').trim()
    return {
      text: `换好了。${label}换成「${dishText}」，这一餐 ${res.slot.kcal} kcal，油盐没有额外增加。方案还是草稿，确认后才会写进右侧。`,
      blocks: [mealCardBlock(plan), anchorBlock([{ panel: 'current_plan', label: '查看当前规划' }])]
    }
  }

  /* 2. 选用某个候选 */
  if (has(/选用|就用|选这个|选方案/)) {
    const label = ['早餐', '午餐', '晚餐'].find((l) => message.includes(l)) || '午餐'
    const res = chooseCandidate(label, message)
    if (!res) {
      return { text: '我没听清是哪个候选，可以把候选名称发我，或直接点候选卡片。', blocks: [] }
    }
    return {
      text: `已选定「${res.candidate.name.split('·').slice(1).join('·').trim()}」，${label} ${res.slot.kcal} kcal，总数已经重新算过。`,
      blocks: [mealCardBlock(getCurrentPlan())]
    }
  }

  /* 3. 确认 / 固定 */
  if (has(/确认|固定|就这个|可以了|没问题/)) {
    const plan = confirmPlan()
    if (!plan) {
      return {
        text: '现在还没有待确认的方案。我可以先按你的档案排今天的三餐，也可以排一周。',
        blocks: [anchorBlock([{ panel: 'current_plan', label: '打开当前规划' }])]
      }
    }
    const list = getShoppingList(plan.plan_id)
    const total = list.groups.reduce((s, g) => s + g.items.length, 0)
    return {
      text: `已确认，方案已生效。右侧「当前规划」和「食材清单」同步完成，清单共 ${total} 项，按类别分好了。`,
      blocks: [
        mealCardBlock(plan),
        shoppingBlock(list),
        anchorBlock([
          { panel: 'current_plan', label: '当前规划' },
          { panel: 'grocery', label: '食材清单' },
          { panel: 'history', label: '历史方案' }
        ])
      ]
    }
  }

  /* 4. 膳食报告 */
  if (has(/报告|复盘/)) {
    const scope = has(/月|30天|30 天/) ? 'month' : 'week'
    const report = generateReport(scope)
    return {
      text: `已为你生成${scope === 'week' ? '上周' : '本月'}膳食报告，覆盖 ${report.meta.valid_days} 天、${report.meta.total_meals} 餐。点「展开查看」看完整分析，右侧「膳食报告」里也能回看。`,
      blocks: [reportBlock(report), sourcesBlock(), anchorBlock([{ panel: 'report', label: '打开膳食报告' }])]
    }
  }

  /* 5. 看完整食谱 */
  if (has(/完整食谱|详细食谱|做法|步骤/)) {
    const plan = getCurrentPlan()
    if (!plan) return { text: '还没有方案可以展开。要先排今天的三餐吗？', blocks: [] }
    return {
      text: '完整食谱在下面，每道菜都有估量、热量和做法。份量按身高体重估算，只作参考。',
      blocks: [mealPlanBlock(plan), nutritionBlock(plan), sourcesBlock()]
    }
  }

  /* 6. 食材清单 */
  if (has(/食材|清单|买菜|采购/)) {
    const list = getShoppingList()
    if (!list) return { text: '方案还没确认，清单暂时是空的。确认后我会按三餐把食材归好类。', blocks: [anchorBlock([{ panel: 'grocery', label: '打开食材清单' }])] }
    return {
      text: `清单已经整理好，共 ${list.groups.reduce((s, g) => s + g.items.length, 0)} 项，按类别分好了。`,
      blocks: [shoppingBlock(list), anchorBlock([{ panel: 'grocery', label: '打开食材清单' }])]
    }
  }

  /* 7. 一周 / 单餐 / 一日三餐 */
  if (has(/一周|七天|7天|整周|一周食谱/)) {
    const plan = createPlan('week')
    return { text: planIntro(plan), blocks: [mealCardBlock(plan), nutritionBlock(plan), sourcesBlock(), anchorBlock([{ panel: 'current_plan', label: '查看当前规划' }])] }
  }
  if (has(/一餐|推荐|午餐|晚餐|早餐/) && !has(/三餐|一日/)) {
    const plan = createPlan('meal')
    return { text: planIntro(plan), blocks: [mealCardBlock(plan)] }
  }
  if (has(/三餐|一日|今天|明天|吃什么|搭配/)) {
    const plan = createPlan('day')
    return { text: planIntro(plan), blocks: [mealCardBlock(plan), nutritionBlock(plan), sourcesBlock(), anchorBlock([{ panel: 'current_plan', label: '查看当前规划' }])] }
  }

  /* 8. 微量 / 症状咨询 */
  if (has(/微量|营养|缺什么|乏力|掉发|头晕|抽筋|便秘/)) {
    return {
      text: '先说结论：单看一份食谱判断不了你身上的具体症状，但可以从你近七天的摄入趋势看缺口。你日记里维生素 C 和钙的达标天数偏少，先按方案把这两项补上，观察 2～4 周。如果症状持续或加重，建议直接就医，别靠调整饮食硬扛。',
      blocks: [
        {
          type: 'medical_hint',
          level: 'warn',
          title: '这不是医学诊断',
          text: '营养建议只作饮食参考，不能替代检查与诊断。出现持续乏力、明显掉发、心慌等情况，请先到正规医院就诊。',
          action_label: '查看参考来源'
        },
        sourcesBlock()
      ]
    }
  }

  /* 9. 兜底闲聊 */
  return {
    text: '这个我暂时答不好。可以让我按档案排今天的三餐、换一餐的候选、或者生成一份膳食报告，这几件事我做得稳一些。',
    blocks: [anchorBlock([{ panel: 'current_plan', label: '当前规划' }, { panel: 'report', label: '膳食报告' }])]
  }
}

/* ================= SSE ================= */

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

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
  const result = routeIntent(body.message)

  send('message', { conversation_id: conversationId, delta: '' })
  await sleep(220)

  // 正文增量：按 4～8 字切片，模拟 token 流
  const text = result.text || ''
  let i = 0
  while (i < text.length) {
    const step = 3 + Math.floor(Math.random() * 5)
    send('message', { delta: text.slice(i, i + step) })
    i += step
    await sleep(28)
  }

  // 结构化边车：正文结束后一次性下发
  if (result.blocks && result.blocks.length) {
    await sleep(60)
    send('message', { meta: { blocks: result.blocks }, conversation_id: conversationId })
  }

  send('done', { conversation_id: conversationId, message_id: `msg_${Date.now()}`, finish_reason: 'stop', suggestions: buildSuggestions(result.blocks) })
  res.end()
}

function buildSuggestions(blocks) {
  const types = (blocks || []).map((b) => b.type)
  if (types.includes('meal_card')) return ['换一换', '看完整食谱', '确认当前方案']
  if (types.includes('report')) return ['生成月膳食报告', '看看食材清单']
  return ['生成一日三餐', '生成一周食谱', '推荐一餐搭配']
}

/* ================= HTTP 入口 ================= */

async function handle(req, res, pathname, searchParams) {
  const token = req.headers['authorization']
  if (!token) {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify(fail(1002, '登录状态已失效，请重新登录')))
    return
  }

  const json = (payload, status = 200) => {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify(payload))
  }

  /* ---- 对话（SSE） ---- */
  if (pathname === '/agent/chat' && req.method === 'POST') {
    const body = await readBody(req)
    if (!body.message || !String(body.message).trim()) {
      json(fail(2002, 'message 不能为空'))
      return
    }
    await streamChat(req, res, body)
    return
  }

  /* ---- 档案 ---- */
  if (pathname === '/profile' && req.method === 'GET') {
    await sleep(80)
    json(ok({ profile: getProfile() }))
    return
  }
  if (pathname === '/profile' && req.method === 'PUT') {
    const body = await readBody(req)
    if (body.height_cm !== undefined && !(Number(body.height_cm) >= 100 && Number(body.height_cm) <= 230)) {
      json(fail(2002, '身高需在 100～230 cm 之间'))
      return
    }
    if (body.weight_kg !== undefined && !(Number(body.weight_kg) >= 30 && Number(body.weight_kg) <= 200)) {
      json(fail(2002, '体重需在 30～200 kg 之间'))
      return
    }
    if (body.age !== undefined && !(Number(body.age) >= 12 && Number(body.age) <= 100)) {
      json(fail(2002, '年龄需在 12～100 岁之间'))
      return
    }
    await sleep(120)
    json(ok({ profile: saveProfile(body) }))
    return
  }

  /* ---- 方案 ---- */
  if (pathname === '/meal-plan/current' && req.method === 'GET') {
    await sleep(80)
    const plan = getCurrentPlan()
    if (!plan) {
      json(empty('还没有生效的方案，先和膳宝聊一句试试'))
      return
    }
    json(ok({ plan }))
    return
  }
  if (pathname === '/meal-plan/list' && req.method === 'GET') {
    await sleep(80)
    json(ok({ plans: listPlans() }))
    return
  }
  const planMatch = pathname.match(/^\/meal-plan\/([^/]+)$/)
  if (planMatch && req.method === 'GET' && !['current', 'list'].includes(planMatch[1])) {
    await sleep(80)
    const plan = getPlanById(decodeURIComponent(planMatch[1]))
    if (!plan) {
      json(empty('这个方案不存在，可能已经被删掉了'))
      return
    }
    json(ok({ plan }))
    return
  }

  /* ---- 食材清单 ---- */
  if (pathname === '/shopping-list' && req.method === 'GET') {
    await sleep(90)
    const list = getShoppingList(searchParams.get('meal_plan_id') || undefined)
    if (!list) {
      json(empty('方案确认后才会生成食材清单'))
      return
    }
    json(ok({ shopping_list: list }))
    return
  }

  /* ---- 膳食报告 ---- */
  if (pathname === '/nutrition/report' && req.method === 'GET') {
    await sleep(90)
    const report = getNutritionReport({
      meal_plan_id: searchParams.get('meal_plan_id') || undefined,
      scope: searchParams.get('scope') || undefined
    })
    if (!report) {
      json(empty('还没有可复盘的方案，先确认一份规划吧'))
      return
    }
    json(ok({ report }))
    return
  }

  /* ---- 健康检查 ---- */
  if (pathname === '/health') {
    json(ok({ status: 'ok', mock: true }))
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
          // 兜底：避免 Mock 异常打断前端联调
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
