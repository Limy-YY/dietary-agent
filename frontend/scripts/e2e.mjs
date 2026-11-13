/**
 * 端到端联调脚本（对着 Mock 后端跑，验证契约与链路）
 *
 * 用法：
 *   1) 另开一个终端：npm run dev
 *   2) npm run e2e
 *   可选环境变量：E2E_BASE（默认 http://127.0.0.1:5173）
 */
import assert from 'node:assert/strict'

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5173'
const TOKEN = process.env.E2E_TOKEN || 'demo-jwt-token'

let passed = 0
const failures = []

function step(name) {
  return {
    ok(detail = '') {
      passed += 1
      console.log(`  \u2713 ${name}${detail ? ' — ' + detail : ''}`)
    },
    fail(err) {
      failures.push({ name, err })
      console.log(`  \u2717 ${name} — ${err.message}`)
    }
  }
}

async function api(path, { method = 'GET', body, token = TOKEN } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  })
  const text = await res.text()
  let json = null
  try {
    json = JSON.parse(text)
  } catch (e) {
    throw new Error(`非 JSON 响应（${res.status}）：${text.slice(0, 120)}`)
  }
  return json
}

/** 读一次 SSE，返回 { text, metas, suggestions, events } */
async function chat(message, conversationId = null) {
  const res = await fetch(`${BASE}/api/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${TOKEN}`
    },
    body: JSON.stringify({ conversation_id: conversationId, message })
  })
  if (!res.ok) throw new Error(`SSE 请求失败：${res.status}`)

  const type = res.headers.get('content-type') || ''
  assert.ok(type.includes('text/event-stream'), `content-type 应为 text/event-stream，实际 ${type}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let text = ''
  let metas = []
  let suggestions = []
  let events = []
  let convId = conversationId

  const handle = (chunk) => {
    let event = 'message'
    const dataLines = []
    chunk.split(/\r?\n/).forEach((line) => {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    })
    if (!dataLines.length) return
    let data = dataLines.join('\n')
    try {
      data = JSON.parse(data)
    } catch (e) {
      /* 保留字符串 */
    }
    events.push(event)
    if (event === 'message') {
      if (typeof data.delta === 'string') text += data.delta
      if (data.meta) metas.push(data.meta)
      if (data.conversation_id) convId = data.conversation_id
    } else if (event === 'done') {
      suggestions = Array.isArray(data.suggestions) ? data.suggestions : []
      if (data.conversation_id) convId = data.conversation_id
    } else if (event === 'error') {
      throw new Error(`SSE error 事件：${data.message || '未知错误'}`)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep = buffer.indexOf('\n\n')
    while (sep !== -1) {
      handle(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
      sep = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) handle(buffer)

  return { text, metas, suggestions, events, convId }
}

function blocksOf(meta) {
  if (!meta) return []
  if (Array.isArray(meta.blocks)) return meta.blocks
  return []
}

function findBlock(metas, type) {
  for (const m of metas) {
    const hit = blocksOf(m).find((b) => b.type === type)
    if (hit) return hit
  }
  return null
}

async function main() {
  console.log(`\n端到端联调 · ${BASE}\n`)

  /* 0. 服务可达 */
  {
    const s = step('GET /api/health')
    try {
      const r = await api('/api/health')
      assert.equal(r.code, 0)
      assert.equal(r.data.mock, true)
      s.ok('Mock 后端在线')
    } catch (e) {
      s.fail(e)
      console.log('\n先启动 dev server：npm run dev\n')
      process.exit(1)
    }
  }

  /* 1. 登录态校验 */
  {
    const s = step('无 Authorization → 1002')
    try {
      const r = await api('/api/profile', { token: '' })
      assert.equal(r.code, 1002)
      s.ok(r.message)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 2. 档案 */
  let profile
  {
    const s = step('GET /api/profile')
    try {
      const r = await api('/api/profile')
      assert.equal(r.code, 0)
      profile = r.data.profile
      assert.ok(profile.height_cm && profile.weight_kg, '档案缺少身体数据')
      s.ok(`${profile.extras.name} · ${profile.height_cm}cm / ${profile.weight_kg}kg · 目标 ${profile.extras.target_energy_kcal} kcal`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 3. 对话：生成今日三餐 */
  let convId = null
  let dayCard
  {
    const s = step('对话「今天吃什么」→ meal_card')
    try {
      const r = await chat('今天吃什么')
      convId = r.convId
      assert.ok(r.text.length > 0, '正文为空')
      assert.ok(r.events.includes('done'), '缺少 done 事件')
      dayCard = findBlock(r.metas, 'meal_card')
      assert.ok(dayCard, 'meta 缺少 meal_card')
      assert.equal(dayCard.scope, 'day')
      assert.equal(dayCard.status, 'draft')
      assert.equal(dayCard.slots.length, 3, '今日卡应有 3 餐')
      s.ok(`正文 ${r.text.length} 字 · ${dayCard.slots.map((x) => x.label + ' ' + x.kcal).join(' / ')}`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 4. 换候选 */
  let lunchBefore
  {
    const s = step('对话「更换午餐候选」→ 午餐变化')
    try {
      assert.ok(dayCard, '上一步失败，跳过')
      lunchBefore = dayCard.slots.find((x) => x.meal_type === 'lunch').dish_text
      const r = await chat('更换午餐候选', convId)
      const card = findBlock(r.metas, 'meal_card')
      assert.ok(card, 'meta 缺少 meal_card')
      const lunch = card.slots.find((x) => x.meal_type === 'lunch')
      assert.notEqual(lunch.dish_text, lunchBefore, '午餐没有变化')
      assert.equal(card.status, 'draft', '换候选后应退回草稿')
      s.ok(`${lunchBefore.slice(0, 14)}… → ${lunch.dish_text.slice(0, 14)}…`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 5. 确认 → shopping_list 边车 */
  let planId = null
  {
    const s = step('对话「确认当前方案」→ fixed + shopping_list')
    try {
      const r = await chat('确认当前方案', convId)
      const card = findBlock(r.metas, 'meal_card')
      const shop = findBlock(r.metas, 'shopping_list')
      assert.ok(card, 'meta 缺少 meal_card')
      assert.equal(card.status, 'fixed', '确认后应为 fixed')
      assert.ok(shop && shop.groups.length, '缺少 shopping_list 分组')
      planId = card.plan_id
      s.ok(`方案 ${planId} · 清单 ${shop.groups.length} 组`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 6. REST 回读：当前方案 / 清单 / 报告 / 历史 */
  {
    const s = step('GET /api/meal-plan/current 与清单、报告一致')
    try {
      const cur = await api('/api/meal-plan/current')
      assert.equal(cur.code, 0)
      assert.equal(cur.data.plan.status, 'fixed')
      assert.equal(cur.data.plan.plan_id, planId)

      const shop = await api('/api/shopping-list?meal_plan_id=' + encodeURIComponent(planId))
      assert.equal(shop.code, 0, '清单应可读')
      const groups = shop.data.shopping_list.groups
      assert.ok(groups.length >= 3, '清单分组过少')

      const rep = await api('/api/nutrition/report?meal_plan_id=' + encodeURIComponent(planId))
      assert.equal(rep.code, 0, '报告应可读')
      const report = rep.data.report
      assert.equal(report.macro.segments.length, 3, '宏量应有 3 段')
      assert.equal(report.micro.items.length, 7, '微量应有 7 项')

      const list = await api('/api/meal-plan/list')
      assert.equal(list.code, 0)
      assert.ok(list.data.plans.some((p) => p.plan_id === planId), '历史列表缺少该方案')
      s.ok(`${groups.length} 组食材 · 宏量 3 段 · 微量 7 项 · 历史 ${list.data.plans.length} 份`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 7. 报告卡（周） */
  {
    const s = step('对话「生成周膳食报告」→ report 卡')
    try {
      const r = await chat('生成周膳食报告', convId)
      const rep = findBlock(r.metas, 'report')
      assert.ok(rep, 'meta 缺少 report')
      assert.equal(rep.micro.items.length, 7)
      assert.ok(rep.daily_trend.length >= 7, '趋势天数不足')
      s.ok(`${rep.headline} · ${rep.meta.valid_days} 天 / ${rep.meta.total_meals} 餐`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 8. 单餐候选 */
  {
    const s = step('对话「推荐一餐搭配」→ 单餐 3 候选')
    try {
      const r = await chat('推荐一餐搭配', convId)
      const card = findBlock(r.metas, 'meal_card')
      assert.ok(card, 'meta 缺少 meal_card')
      assert.equal(card.scope, 'meal')
      assert.equal(card.slots.length, 1, '单餐卡应只有 1 个 slot')
      assert.equal(card.slots[0].candidates.length, 3, '应有 3 个候选')
      s.ok(`${card.slots[0].label} · ${card.slots[0].candidates.map((c) => c.name.split(' · ')[0]).join(' / ')}`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 9. 档案写回 */
  {
    const s = step('PUT /api/profile → 能量目标重算')
    try {
      const current = Number(profile.weight_kg)
      const target = current === 62 ? 60 : 62 // 幂等：重复跑也能造出变化
      const before = profile.extras.target_energy_kcal
      const r = await api('/api/profile', { method: 'PUT', body: { weight_kg: target } })
      assert.equal(r.code, 0)
      assert.equal(Number(r.data.profile.weight_kg), target)
      assert.notEqual(r.data.profile.extras.target_energy_kcal, before, '目标能量未重算')
      profile = r.data.profile
      s.ok(`${current}kg → ${target}kg，目标 ${before} → ${r.data.profile.extras.target_energy_kcal} kcal`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 10. 参数校验 */
  {
    const s = step('空 message → 2002')
    try {
      const r = await api('/api/agent/chat', { method: 'POST', body: { message: '   ' } })
      assert.equal(r.code, 2002)
      s.ok(r.message)
    } catch (e) {
      s.fail(e)
    }
  }

  console.log(`\n结果：通过 ${passed} 项，失败 ${failures.length} 项`)
  if (failures.length) {
    failures.forEach((f) => console.log(` - ${f.name}: ${f.err.message}`))
    process.exit(1)
  }
  console.log('端到端链路 OK：对话 → 生成 → 换候选 → 确认 → 面板同步 → 报告 → 档案\n')
}

main().catch((e) => {
  console.error('\n脚本异常：', e.message)
  process.exit(1)
})
