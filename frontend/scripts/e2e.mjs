/**
 * 端到端联调脚本（v1.2 契约）
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
  try {
    return JSON.parse(text)
  } catch (e) {
    throw new Error(`非 JSON 响应（${res.status}）：${text.slice(0, 120)}`)
  }
}

/**
 * 读一次 SSE，返回 v1.2 事件：
 * { text, artifacts:[{type,payload}], clarifies:[], done, events[], convId }
 */
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
  let events = []
  const artifacts = []
  const clarifies = []
  let done = null
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
      assert.equal(data.type, 'text', 'message 事件必须带 type=text')
      if (typeof data.content === 'string') text += data.content
    } else if (event === 'artifact') {
      artifacts.push({ type: data.type, payload: data.payload || {} })
    } else if (event === 'clarify') {
      clarifies.push(data)
    } else if (event === 'done') {
      done = data
      if (data.conversation_id) convId = data.conversation_id
    } else if (event === 'error') {
      throw new Error(`SSE error 事件：${data.message || '未知错误'}`)
    }
  }

  while (true) {
    const { done: streamDone, value } = await reader.read()
    if (streamDone) break
    buffer += decoder.decode(value, { stream: true })
    let sep = buffer.indexOf('\n\n')
    while (sep !== -1) {
      handle(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
      sep = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) handle(buffer)

  return { text, artifacts, clarifies, done, events, convId }
}

function findArtifact(list, type) {
  return list.find((a) => a.type === type) || null
}

function slotByMeal(card, meal) {
  return (card.slots || []).find((s) => s.meal_type === meal)
}

function selectedDishText(slot) {
  const c = (slot.candidates || []).find((x) => x.candidate_id === slot.selected_candidate_id) || (slot.candidates || [])[0]
  return c ? c.dishes.map((d) => d.name).join(' + ') : ''
}

async function main() {
  console.log(`\n端到端联调（v1.2）· ${BASE}\n`)

  /* 0. 服务可达 */
  {
    const s = step('GET /api/health')
    try {
      const r = await api('/api/health')
      assert.equal(r.code, 0)
      assert.equal(r.data.contract, 'v1.2')
      s.ok('Mock 后端在线（v1.2）')
    } catch (e) {
      s.fail(e)
      console.log('\n先启动 dev server：npm run dev\n')
      process.exit(1)
    }
  }

  /* 0.5 清 mock 状态，保证可重复跑 */
  {
    const s = step('POST /api/__reset（仅 mock）')
    try {
      const r = await api('/api/__reset', { method: 'POST' })
      assert.equal(r.code, 0)
      s.ok('状态已重置')
    } catch (e) {
      s.fail(e)
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

  /* 2. 档案 v1.2 十一字段 */
  let profile
  {
    const s = step('GET /api/profile（v1.2 字段）')
    try {
      const r = await api('/api/profile')
      assert.equal(r.code, 0)
      profile = r.data
      assert.ok(profile.gender && profile.age && profile.height_cm && profile.weight_kg, '必填字段缺失')
      assert.ok(profile.goal_code && profile.goal_name, 'goal_code / goal_name 缺失')
      assert.ok(Array.isArray(profile.cooking_equipment), 'cooking_equipment 应为数组')
      assert.ok(profile.conditions && profile.conditions.hypertension, 'conditions 三态缺失')
      assert.equal(profile.sex, undefined, '不允许再出现 sex 兼容字段')
      assert.ok(Number.isFinite(Number(profile.target_calories)), 'target_calories 缺失')
      s.ok(`${profile.name} · ${profile.gender} ${profile.age}岁 · ${profile.goal_name} · 目标 ${profile.target_calories} kcal`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 3. 对话：今日三餐 → meal_card artifact */
  let convId = null
  let dayCard
  {
    const s = step('对话「今天吃什么」→ message + artifact meal_card')
    try {
      const r = await chat('今天吃什么')
      convId = r.convId
      assert.ok(r.text.length > 0, '正文为空')
      assert.ok(r.events.includes('artifact'), '缺少 artifact 事件')
      assert.ok(r.done, '缺少 done 事件')
      assert.ok(r.done.meal_plan_id != null, 'done 应带 meal_plan_id')
      dayCard = findArtifact(r.artifacts, 'meal_card').payload
      assert.equal(dayCard.plan_type, '日')
      assert.equal(dayCard.status, 'candidates')
      assert.equal(dayCard.slots.length, 3, '今日卡应有 3 个餐位')
      assert.ok(dayCard.slots.every((x) => x.meal_slot_id && x.meal_type && x.candidates.length >= 2), '餐位字段不合规')
      assert.ok(dayCard.slots[0].candidates[0].macro_estimate.kcal != null, '候选缺 macro_estimate')
      assert.ok(dayCard.slots[0].candidates[0].oil_salt_estimate, '候选缺 oil_salt_estimate')
      s.ok(`正文 ${r.text.length} 字 · 方案 ${r.done.meal_plan_id} · ${dayCard.slots.map((x) => x.meal_type + ' ' + selectedDishText(x).slice(0, 8)).join(' / ')}`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 4. 换候选 */
  let lunchBefore
  {
    const s = step('对话「更换午餐候选」→ selected_candidate_id 变化')
    try {
      assert.ok(dayCard, '上一步失败，跳过')
      lunchBefore = slotByMeal(dayCard, '午').selected_candidate_id
      const r = await chat('更换午餐候选', convId)
      const card = findArtifact(r.artifacts, 'meal_card').payload
      const lunch = slotByMeal(card, '午')
      assert.notEqual(lunch.selected_candidate_id, lunchBefore, '午餐候选没有变化')
      assert.equal(card.status, 'candidates', '换候选后仍应是 candidates')
      s.ok(`${lunchBefore} → ${lunch.selected_candidate_id}`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 5. 确认 → fixed + shopping_list */
  let planId = null
  {
    const s = step('对话「确认当前方案」→ fixed + shopping_list')
    try {
      const r = await chat('确认当前方案', convId)
      const card = findArtifact(r.artifacts, 'meal_card').payload
      const shop = findArtifact(r.artifacts, 'shopping_list').payload
      assert.equal(card.status, 'fixed', '确认后应为 fixed')
      assert.ok(shop && shop.groups.length, '缺少 shopping_list 分组')
      assert.ok(shop.groups.every((g) => g.items.every((it) => it.ingredient_id && it.unit)), '清单项缺 ingredient_id/unit')
      assert.ok(shop.groups.every((g) => g.items.every((it) => it.is_staple === undefined)), 'v1.2 不应再出现 is_staple')
      planId = card.meal_plan_id
      s.ok(`方案 ${planId} · ${shop.total_items} 项 / ${shop.groups.length} 组`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 6. REST：current / shopping / report / 分页 */
  {
    const s = step('REST 回读：current / shopping / report / list')
    try {
      const cur = await api('/api/meal-plan/current')
      assert.equal(cur.code, 0)
      assert.equal(cur.data.has_plan, true)
      assert.equal(cur.data.status, 'fixed')
      assert.equal(cur.data.meal_plan_id, planId)
      assert.ok(cur.data.slots.length >= 3)
      assert.ok('dish_names' in cur.data.slots[0], 'current 餐位缺 dish_names')

      const shop = await api('/api/shopping-list?meal_plan_id=' + encodeURIComponent(planId))
      assert.equal(shop.code, 0, '清单应可读')
      assert.equal(shop.data.total_items, shop.data.groups.reduce((n, g) => n + g.items.length, 0))

      const before = await api('/api/nutrition/report?meal_plan_id=' + encodeURIComponent(planId))
      assert.equal(before.code, 1004, '未分析过应返回 1004')

      const analyzed = await api('/api/nutrition/analysis', { method: 'POST', body: { meal_plan_id: planId, window_days: 7 } })
      assert.equal(analyzed.code, 0)
      assert.equal(analyzed.data.report_type, 'plan')
      assert.ok(analyzed.data.macro_summary)
      assert.equal(Object.keys(analyzed.data.key_micro_summary).length, 7, '微量应有 7 键')
      assert.ok(analyzed.data.completeness && analyzed.data.summary.data_quality_notes, '缺完整度/数据说明')

      const after = await api('/api/nutrition/report?meal_plan_id=' + encodeURIComponent(planId))
      assert.equal(after.code, 0)
      assert.equal(after.data.nutrition_report_id, analyzed.data.nutrition_report_id)

      const list = await api('/api/meal-plan/list?page=1&page_size=2')
      assert.equal(list.code, 0)
      assert.equal(list.data.page, 1)
      assert.equal(list.data.page_size, 2)
      assert.ok(list.data.total >= 1)
      assert.ok(list.data.items.every((x) => !('slots' in x)), '列表摘要不应包含 slots')
      s.ok(`${cur.data.slots.length} 个餐位 · 清单 ${shop.data.total_items} 项 · 微量 7 键 · 历史 ${list.data.total} 份`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 7. 报告 artifact */
  {
    const s = step('对话「生成周膳食报告」→ artifact nutrition_report')
    try {
      const r = await chat('生成周膳食报告', convId)
      const rep = findArtifact(r.artifacts, 'nutrition_report').payload
      assert.equal(rep.report_type, 'plan')
      assert.equal(Object.keys(rep.key_micro_summary).length, 7)
      assert.ok(rep.summary.reference_hints.length, '缺 reference_hints')
      const neutral = Object.values(rep.key_micro_summary).filter((m) => m.status === '参考提示').length
      s.ok(`${rep.nutrition_report_id} · ${rep.period_start}~${rep.period_end} · 参考提示 ${neutral} 项`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 8. 单餐候选 */
  {
    const s = step('对话「推荐一餐搭配」→ plan_type 餐 + 3 候选')
    try {
      const r = await chat('推荐一餐搭配', convId)
      const card = findArtifact(r.artifacts, 'meal_card').payload
      assert.equal(card.plan_type, '餐')
      assert.equal(card.slots.length, 1, '单餐卡应只有 1 个 slot')
      assert.equal(card.slots[0].candidates.length, 3, '应有 3 个候选')
      s.ok(`${card.slots[0].meal_type} · ${card.slots[0].candidates.length} 个候选`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 8.1 生成可选参数：meal_types 过滤 + candidates_per_slot */
  {
    const s = step('POST /meal-plan/week/generate → meal_types + candidates_per_slot')
    try {
      const r = await api('/api/meal-plan/week/generate', {
        method: 'POST',
        body: {
          start_date: '2026-11-15',
          end_date: '2026-11-15',
          plan_type: '日',
          meal_types: ['午'],
          candidates_per_slot: 2
        }
      })
      assert.equal(r.code, 0)
      assert.equal(r.data.slots.length, 1, 'meal_types 应只保留午餐')
      assert.equal(r.data.slots[0].candidates.length, 2, 'candidates_per_slot=2 应只下发 2 个候选')
      assert.ok(
        r.data.slots[0].candidates.some((c) => c.candidate_id === r.data.slots[0].selected_candidate_id),
        '选中候选必须在裁剪后的候选列表内'
      )
      s.ok(`1 个餐位 · ${r.data.slots[0].candidates.length} 个候选`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 9. 档案写回 target_calories 重算 */
  {
    const s = step('PUT /api/profile → target_calories 重算')
    try {
      const current = Number(profile.weight_kg)
      const target = current === 62 ? 60 : 62
      const before = profile.target_calories
      const r = await api('/api/profile', { method: 'PUT', body: { weight_kg: target } })
      assert.equal(r.code, 0)
      assert.equal(Number(r.data.weight_kg), target)
      assert.notEqual(r.data.target_calories, before, 'target_calories 未重算')
      assert.equal(r.data.sex, undefined, '兼容列 sex 只读，不应回写')
      profile = r.data
      s.ok(`${current}kg → ${target}kg，目标 ${before} → ${r.data.target_calories} kcal`)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 10. 参数校验 1001 */
  {
    const s = step('空 message → 1001（参数校验）')
    try {
      const r = await api('/api/agent/chat', { method: 'POST', body: { message: '   ' } })
      assert.equal(r.code, 1001)
      s.ok(r.message)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 11. fixed 方案换候选 → 2005 */
  {
    const s = step('fixed 方案换候选 → 2005（不再误报参数错误）')
    try {
      const cur = await api('/api/meal-plan/current')
      const slot = cur.data.slots[0]
      const r = await api('/api/meal-plan/candidate/swap', {
        method: 'POST',
        body: { meal_plan_id: planId, meal_slot_id: slot.meal_slot_id }
      })
      assert.equal(r.code, 2005)
      s.ok(r.message)
    } catch (e) {
      s.fail(e)
    }
  }

  /* 12. goal_code 非法 → 1001 */
  {
    const s = step('PUT /api/profile goal_code 非法 → 1001')
    try {
      const r = await api('/api/profile', { method: 'PUT', body: { goal_code: 'burn_fat' } })
      assert.equal(r.code, 1001)
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
  console.log('端到端链路 OK：档案 → 生成 → 换候选 → 确认 → 面板回读 → 报告 → 错误码\n')
}

main().catch((e) => {
  console.error('\n脚本异常：', e.message)
  process.exit(1)
})
