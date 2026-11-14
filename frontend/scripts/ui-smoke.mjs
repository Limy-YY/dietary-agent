/**
 * UI 冒烟测试（真浏览器，不下载 Chromium，直接用本机 Chrome）
 *
 * 前置：npm run dev 已在 5173 跑着
 * 用法：node scripts/ui-smoke.mjs
 * 产物：docs/screenshots/*.png
 */
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:5173'
const CHROME_CANDIDATES = [
  'C:/Users/30930/AppData/Local/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
]

const shotDir = path.resolve('docs/screenshots')
fs.mkdirSync(shotDir, { recursive: true })

let passed = 0
const failures = []
function ok(name, detail = '') {
  passed += 1
  console.log(`  \u2713 ${name}${detail ? ' — ' + detail : ''}`)
}
function fail(name, e) {
  failures.push(name)
  console.log(`  \u2717 ${name} — ${e.message || e}`)
}

const executablePath = CHROME_CANDIDATES.find((p) => fs.existsSync(p))
if (!executablePath) {
  console.error('没找到 Chrome / Edge，跳过 UI 冒烟')
  process.exit(1)
}

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 920 }, deviceScaleFactor: 1 })
const consoleErrors = []
page.on('pageerror', (e) => consoleErrors.push(String(e)))
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push(m.text())
})

async function shot(name) {
  await page.screenshot({ path: path.join(shotDir, name), fullPage: false })
}

async function say(text) {
  // 上一轮 SSE 还没结束时 store 会拒绝新消息，先等打字点消失
  await page.waitForFunction(() => !document.querySelector('.typing'), null, { timeout: 15000 })
  const before = await page.locator('.msg.ai').count()
  const ta = page.locator('textarea').first()
  await ta.click()
  await ta.fill(text)
  await page.keyboard.press('Enter')
  await page.waitForFunction((n) => document.querySelectorAll('.msg.ai').length > n, before, { timeout: 15000 })
}

try {
  console.log(`\nUI 冒烟 · ${BASE}\n`)

  /* 清 mock 状态，保证空态可复现 */
  await page.request.post(`${BASE}/api/__reset`, {
    headers: { Authorization: 'Bearer demo-jwt-token' }
  })

  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.msg.ai .greet-hi', { timeout: 15000 })
  await page.waitForSelector('.icon-sidebar .tool-icon', { timeout: 10000 })
  ok('首屏渲染：问候语 + 三栏布局')

  /* 开启新对话 → 欢迎页（与 main.html 一致） */
  await page.locator('.new-chat-btn').click()
  await page.waitForSelector('.welcome-screen', { timeout: 10000 })
  ok('开启新对话后展示欢迎页（对齐 main.html）')
  const chipTexts = await page.locator('.preset-chips-wrap .chip').allInnerTexts()
  if (chipTexts.length !== 5) throw new Error(`底部快捷应为 5 个（对齐 main.html），实际 ${chipTexts.length}`)
  ok('底部固定 5 个快捷（对齐 main.html）', chipTexts.join(' / '))
  await shot('01-welcome.png')

  /* 0. 四个面板的初始空态 */
  for (const key of ['grocery', 'current_plan', 'history', 'report']) {
    try {
      await page.locator(`.tool-icon[data-key="${key}"]`).click()
      await page.waitForSelector('.tool-panel .empty-state', { timeout: 8000 })
    } catch (e) {
      throw new Error(`面板 ${key} 初始空态异常：${e.message.split('\n')[0]}`)
    }
    await page.locator('.panel-close').first().click()
    await page.waitForTimeout(250)
  }
  await page.locator('.tool-icon', { hasText: '当前规划' }).click()
  await page.waitForTimeout(300)
  await shot('00-empty-panel.png')
  await page.locator('.panel-close').first().click()
  await page.waitForTimeout(250)
  ok('四个面板初始均为空态（1004 → 空态，不编数据）')

  /* 1. 底部快捷 chip → SSE 生成今日餐卡 */
  await page.locator('.preset-chips-wrap .chip').first().click()
  await page.waitForSelector('.meal-row', { timeout: 25000 })
  await page.waitForSelector('.recipe-card .card-sub', { timeout: 25000 })
  const mealRows = await page.locator('.meal-row').count()
  ok('对话 → 今日餐卡', `${mealRows} 行餐次`)
  await page.waitForTimeout(1500)
  await shot('02-day-plan.png')

  /* 2. 换一换（午餐） */
  const lastCard = page.locator('.recipe-card').last()
  const lunchRow = lastCard.locator('.meal-row').nth(1)
  const before = await lunchRow.locator('.meal-dish').innerText()
  await lunchRow.locator('.swap-btn').click()
  await page.waitForFunction(
    (prev) => {
      const cards = document.querySelectorAll('.recipe-card')
      const card = cards[cards.length - 1]
      const rows = card ? card.querySelectorAll('.meal-row') : []
      const dish = rows[1] && rows[1].querySelector('.meal-dish')
      return dish && dish.textContent.trim() !== prev
    },
    before,
    { timeout: 25000 }
  )
  const after = await page.locator('.recipe-card').last().locator('.meal-row').nth(1).locator('.meal-dish').innerText()
  ok('换候选 → 午餐菜品变化', before.slice(0, 16) + '… → ' + after.slice(0, 16) + '…')
  await shot('03-swapped.png')

  /* 3. 详细食谱弹窗 */
  await page.locator('.recipe-card').last().locator('.meal-row').first().click()
  await page.waitForSelector('.el-dialog', { timeout: 8000 })
  const dialogTitle = await page.locator('.el-dialog__title').innerText()
  await page.waitForTimeout(700)
  ok('单餐点击 → 详细食谱弹窗', dialogTitle)
  await shot('04-recipe-modal.png')
  await page.locator('.el-dialog__footer button', { hasText: '关闭' }).first().click()
  await page.waitForTimeout(400)

  /* 4. 确认 → 面板同步 */
  const fixBtn = page.locator('.fix-btn:not([disabled])').last()
  await fixBtn.click()
  await page.waitForSelector('.status-tag.fixed', { timeout: 20000 })
  ok('确认当前方案 → 餐卡置为已生效')

  await page.locator('.tool-icon', { hasText: '当前规划' }).click()
  await page.waitForSelector('.tool-panel .plan-overview', { timeout: 10000 })
  const planTag = await page.locator('.tool-panel .plan-overview .type-tag').innerText()
  if (!planTag.includes('已生效')) throw new Error(`当前规划面板状态异常：${planTag}`)
  await page.waitForTimeout(400)
  ok('面板 · 当前规划显示服务端状态', planTag)
  await shot('05-panel-current.png')

  await page.locator('.tool-icon', { hasText: '食材清单' }).click()
  await page.waitForSelector('.tool-panel .grocery-item', { timeout: 12000 })
  const groceryCount = await page.locator('.tool-panel .grocery-item').count()
  const grocerySample = await page.locator('.tool-panel .grocery-item').first().innerText()
  await page.waitForTimeout(400)
  if (!/\d/.test(grocerySample)) throw new Error(`食材清单没有估算量：${grocerySample.replace(/\n/g, ' ')}`)
  ok('面板 · 食材清单有真实分组条目', `${groceryCount} 项 · ${grocerySample.replace(/\n/g, ' ')}`)
  await shot('06-panel-grocery.png')

  await page.locator('.tool-icon', { hasText: '膳食报告' }).click()
  await page.waitForSelector('.tool-panel .empty-state', { timeout: 12000 })
  await page.locator('.tool-panel .es-action', { hasText: '生成本方案膳食报告' }).click()
  await page.waitForSelector('.tool-panel .rp-section-title', { timeout: 25000 })
  const reportTitle = await page.locator('.tool-panel .rp-insights h5').first().innerText()
  await page.waitForSelector('.tool-panel .rp-quality', { timeout: 10000 })
  await page.waitForTimeout(400)
  ok('面板 · 膳食报告（方案级 CTA → 宏量 + 微量 + 数据质量）', reportTitle)
  await shot('07-panel-report.png')

  await page.locator('.tool-icon', { hasText: '历史方案' }).click()
  await page.waitForSelector('.tool-panel .history-plan', { timeout: 10000 })
  const historyCount = await page.locator('.tool-panel .history-plan').count()
  await page.waitForTimeout(400)
  ok('面板 · 历史方案列表', `${historyCount} 份`)
  await shot('08-panel-history.png')

  /* 5. 周视图 / 单餐 / 就医提示 */
  await page.locator('.panel-close').first().click()
  await page.waitForTimeout(300)

  await say('排一周食谱')
  await page.waitForSelector('.week-list .week-day', { timeout: 25000 })
  const weekDays = await page.locator('.week-list .week-day').count()
  await page.locator('.week-list .week-day').first().click()
  await page.waitForTimeout(600)
  ok('周视图：7 天折叠卡（首日展开）', `${weekDays} 天`)
  await shot('10-week-plan.png')

  await say('推荐一餐搭配')
  await page.waitForSelector('.cand-list .cand', { timeout: 25000 })
  const candCount = await page.locator('.cand-list .cand').count()
  await page.waitForTimeout(500)
  ok('单餐视图：多候选卡', `${candCount} 个候选`)
  await shot('11-single-meal.png')

  await say('最近总乏力掉发，缺什么营养')
  await page.waitForTimeout(1200)
  const aiText = await page.locator('.msg.ai').last().innerText()
  if (!aiText.includes('就医')) throw new Error('症状咨询没有给出就医边界')
  ok('症状咨询：给出就医边界（v1.2 无 medical_hint artifact）')
  await shot('12-medical-hint.png')

  /* 5.1 对话里生成报告 → 右侧「膳食报告」面板必须能回看（不再是空态） */
  await say('生成周膳食报告')
  await page.waitForSelector('.report-card', { timeout: 25000 })
  const chatReportMeta = await page.locator('.report-card .rc-meta').last().innerText()
  if (!/\d{4}-\d{2}-\d{2}/.test(chatReportMeta)) throw new Error(`对话内报告卡缺日期区间：${chatReportMeta}`)
  ok('对话内报告卡带日期区间与餐数', chatReportMeta.replace(/\n/g, ' '))
  await page.locator('.tool-icon[data-key="report"]').click()
  await page.waitForSelector('.tool-panel .rp-insights', { timeout: 12000 })
  await page.waitForFunction(() => !document.querySelector('.tool-panel .sk-wrap'), null, { timeout: 12000 })
  const panelReportTitle = await page.locator('.tool-panel .rp-insights h5').first().innerText()
  const panelQuality = await page.locator('.tool-panel .rp-quality').innerText()
  if (!/已知\s*3\s*餐/.test(panelQuality)) throw new Error(`报告完整度与实际餐数不符：${panelQuality.replace(/\n/g, ' ')}`)
  await page.waitForTimeout(500)
  ok('对话生成报告 → 报告面板同步', panelReportTitle)
  await shot('14-report-panel-after-gen.png')
  await page.locator('.panel-close').first().click()
  await page.waitForTimeout(300)

  /* 6. 轻量档案 */
  await page.locator('.user-profile-btn').click()
  await page.locator('.menu-item', { hasText: '个人档案' }).click()
  await page.waitForSelector('.profile-hero', { timeout: 8000 })
  const profileName = await page.locator('.ph-name').innerText()
  await page.waitForTimeout(700)
  ok('轻量档案弹窗（查看态）', profileName)
  await shot('09-profile.png')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(600)

  /* 6. 控制台无异常 */
  if (consoleErrors.length) {
    throw new Error(`控制台报错 ${consoleErrors.length} 条：${consoleErrors.slice(0, 3).join(' | ')}`)
  }
  ok('控制台无 JS 报错')
} catch (e) {
  fail('UI 冒烟', e)
  try {
    await shot('99-failure.png')
  } catch (err) {
    /* 截图失败忽略 */
  }
} finally {
  await browser.close()
}

console.log(`\n结果：通过 ${passed} 项，失败 ${failures.length} 项；截图在 docs/screenshots/`)
if (failures.length) process.exit(1)
console.log('UI 链路 OK：空态 → 生成 → 换候选 → 食谱弹窗 → 确认 → 四面板 → 周视图/单餐/就医 → 档案\n')
