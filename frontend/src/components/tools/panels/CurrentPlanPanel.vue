<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 55%"></div>
      <div class="skeleton sk-line" style="width: 80%"></div>
      <div class="skeleton sk-line" style="width: 40%"></div>
    </div>

    <template v-else-if="plan">
      <div class="data-timestamp">🕒 {{ plan.status === 'fixed' ? '固定于' : '更新于' }} {{ updatedText }}</div>

      <div class="plan-overview">
        <div class="po-head">
          <div>
            <div class="po-title">{{ plan.title || '当前规划' }}</div>
            <div class="po-target">{{ plan.range_text }}</div>
          </div>
          <span class="type-tag" :class="isFixed ? 'live' : 'archive'">{{ isFixed ? '已生效' : '待确认' }}</span>
        </div>
        <div class="po-cal-compact">
          <span class="num">{{ fmtKcal(actualKcal) }}</span>
          <span class="unit">{{ kcalLabel }} · 目标 {{ fmtKcal(plan.goal_energy_kcal) }} kcal</span>
        </div>
        <div v-if="kcalPct !== null" class="po-cal-bar">
          <div class="po-cal-fill" :style="{ width: kcalPct + '%' }"></div>
        </div>
        <div class="po-cal-sub">目标为份量量级参考，不做热量缺口/盈余</div>
      </div>

      <div class="section-head-row">
        <div class="section-head-title">🍽️ 食谱概览</div>
        <button class="expand-all-btn" @click="toggleAllDays">{{ allOpen ? '全部收起' : '全部展开' }}</button>
      </div>

      <div
        v-for="(day, di) in plan.days"
        :key="day.iso + di"
        class="plan-day"
        :class="{ open: isOpen(di) }"
      >
        <div class="plan-day-head" @click="toggleDay(di)">
          <span class="pd-label">{{ day.is_today ? '今天' : day.weekday }} · {{ day.date }}</span>
          <span class="pd-kcal">{{ fmtKcal(day.kcal) }} kcal</span>
          <span class="pd-chevron">▾</span>
        </div>
        <div class="plan-day-body">
          <div class="meal-overview-wrap">
            <table class="meal-table">
              <thead>
                <tr><th class="mt-meal">餐次</th><th class="mt-dish">菜品</th><th class="mt-kcal">热量</th></tr>
              </thead>
              <tbody>
                <tr v-for="(slot, si) in day.slots" :key="si">
                  <td class="mt-meal">{{ slot.label }}</td>
                  <td class="mt-dish">{{ slot.dish_text || '—' }}</td>
                  <td class="mt-kcal">
                    <span class="num">{{ fmtKcal(slot.kcal) }}</span><span class="unit"> kcal</span>
                    <button v-if="!isFixed" class="cp-swap" :disabled="!slot.candidates.length || swapping === slot.slot_id" @click="swap(slot)">{{ swapping === slot.slot_id ? '换一换…' : '换一换' }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="plan-actions">
        <button class="plan-btn-secondary" @click="openRecipe">看完整食谱</button>
        <button v-if="!isFixed" class="fix-btn" @click="confirmPlan">确认方案</button>
      </div>
      <button class="cp-report-link" :disabled="reportLoading" @click="openReport">
        📊 {{ reportLoading ? '正在查看…' : '查看这份方案的膳食报告' }} →
      </button>
      <div class="panel-note">{{ isFixed ? '💡 方案已生效，右侧「食材清单」已按天同步采购项，建议分批购买。' : '💡 确认方案后，「食材清单」才会同步更新采购项。' }}</div>

      <div
        v-if="plan.reference_hints.length"
        class="plan-nutrition"
      >
        <div class="plan-nutrition-title">🥗 营养提示</div>
        <ul class="plan-nutrition-list">
          <li v-for="(h, i) in plan.reference_hints" :key="'h' + i">{{ h }}</li>
        </ul>
      </div>

      <div v-if="plan.data_quality_notes.length" class="plan-data-notes">
        <button class="pdn-toggle" @click="showDataNotes = !showDataNotes">
          <span>📌 数据说明</span>
          <span class="pdn-count">{{ plan.data_quality_notes.length }}</span>
          <span class="pdn-chevron">{{ showDataNotes ? '▾' : '▸' }}</span>
        </button>
        <ul v-if="showDataNotes" class="pdn-list">
          <li v-for="(n, i) in plan.data_quality_notes" :key="'n' + i">{{ n }}</li>
        </ul>
      </div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="📅"
        title="暂无进行中的规划"
        desc="还没有固定下来的方案。
配餐并确认后，可在这里查看每一餐的菜品与热量。"
        :actions="[{ icon: '✨', label: '生成一日三餐', desc: '先让智能体为你配餐并确认', phrase: '生成一日三餐' }]"
        hint="💡 生成后记得在卡片或这里点 <b>“确认方案”</b>，方案固定后才会更新。"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchCurrentPlan } from '@/api/mealPlan.js'
import { fetchReport } from '@/api/nutrition.js'
import { fmtKcal, normalizeCurrentPlan } from '@/utils/schema.js'
import { fmtDateTime } from '@/utils/format.js'
import { PHRASE } from '@/constants/actions.js'
import { usePanelStore } from '@/stores/panel.js'
import { useChatStore } from '@/stores/chat.js'
import { useUi } from '@/composables/useUi.js'
import EmptyState from '@/components/common/EmptyState.vue'

const panel = usePanelStore()
const chat = useChatStore()
const ui = useUi()

const loading = ref(false)
const error = ref('')
const plan = ref(null)
const openDays = ref([])
// 「数据说明」脚注默认折叠（内容偏数据口径，不属于上方「营养提示」）
const showDataNotes = ref(false)
// 正在「换一换」的餐位 slot_id（用于按钮 spinner / 禁用）
const swapping = ref('')
// 正在检查/加载方案级膳食报告
const reportLoading = ref(false)

const isFixed = computed(() => plan.value?.status === 'fixed')
const updatedText = computed(() => {
  const t = plan.value?.fixed_at
  return t ? fmtDateTime(t) : '—'
})

/** 实际热量：单餐/单日取总量，多日取日均（goal_energy_kcal 为每日量级） */
const actualKcal = computed(() => {
  const days = plan.value?.days || []
  const known = days
    .map((d) => d.kcal)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
  if (!known.length) return null
  const total = known.reduce((s, v) => s + Number(v), 0)
  return plan.value?.plan_type === '餐' || days.length <= 1 ? total : total / known.length
})

const kcalLabel = computed(() => {
  if (plan.value?.plan_type === '餐') return '本餐'
  if ((plan.value?.days?.length || 0) <= 1) return '全天'
  return '日均'
})

/** 达成度：仅作量级参考展示，cap 在 0~100 */
const kcalPct = computed(() => {
  const a = actualKcal.value
  const g = plan.value?.goal_energy_kcal
  if (a == null || g == null || !(g > 0)) return null
  return Math.min(100, Math.max(0, Math.round((a / g) * 100)))
})

const allOpen = computed(() => {
  const n = plan.value?.days?.length || 0
  return n > 0 && openDays.value.length === n
})

function isOpen(di) {
  return openDays.value.includes(di)
}

function toggleDay(di) {
  const i = openDays.value.indexOf(di)
  if (i >= 0) openDays.value.splice(i, 1)
  else openDays.value.push(di)
}

function toggleAllDays() {
  const days = plan.value?.days || []
  openDays.value = allOpen.value ? [] : days.map((_, i) => i)
}

async function swap(slot) {
  if (isFixed.value || chat.sending || swapping.value) return
  swapping.value = slot.slot_id
  try {
    await chat.silentAction(PHRASE.swap(slot.label || '这一餐'), {
      meal_plan_id: plan.value?.plan_id,
      meal_slot_id: slot.slot_id,
      action: 'swap_candidate'
    })
  } catch (e) {
    ElMessage(e.message || '换候选失败，请重试')
  } finally {
    swapping.value = ''
  }
  // 换完本地刷新自身：面板可能正在展示这份「待确认」方案，而换候选只改草稿、不再触发全局 bump
  await load()
}

async function openReport() {
  if (reportLoading.value) return
  const pid = plan.value?.plan_id
  if (!pid) return
  reportLoading.value = true
  try {
    // 已有方案级复盘 → 直接弹报告弹窗（只读，符合「面板只承载展示」）
    const existing = await fetchReport({ mealPlanId: pid })
    if (existing) {
      ui.reportPayload = existing
      ui.reportOpen = true
      return
    }
    // 无复盘：未固定先引导固定（draft/candidates 没有已选候选，无法分析）
    if (!isFixed.value) {
      ElMessage('请先「确认方案」，方案固定后才能生成营养复盘')
      return
    }
    // 已固定 → 走对话生成（对话为唯一入口），报告内嵌进对话气泡并落库
    chat.send(PHRASE.report)
  } catch (e) {
    // 拦截器已对业务/网络错误统一 toast，这里只重置状态，避免重复提示
  } finally {
    reportLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const raw = await fetchCurrentPlan()
    const view = raw ? normalizeCurrentPlan(raw) : null
    plan.value = view && view.has_plan ? view.plan : null
    const days = plan.value?.days || []
    const todayIdx = days.findIndex((d) => d.is_today)
    openDays.value = days.length ? [todayIdx >= 0 ? todayIdx : 0] : []
  } catch (e) {
    error.value = e.message || '方案加载失败'
    plan.value = null
  } finally {
    loading.value = false
  }
}

async function confirmPlan() {
  if (!plan.value?.plan_id) return
  try {
    await chat.silentAction(PHRASE.confirm, {
      meal_plan_id: plan.value.plan_id,
      action: 'confirm'
    })
    await load()
  } catch (e) {
    if (e && e.code === 2005) {
      // 同期已有固定方案冲突：与 MealCardBlock.onConfirm 对齐，退回对话路径发起「替换/取消」追问，
      // 而不是只弹一句裸警告让用户卡住（BUG-046）。
      await chat.send(PHRASE.confirm)
    } else {
      ElMessage(e.message || '确认失败，请重试')
    }
  }
}

function openRecipe() {
  if (!plan.value) return
  ui.recipePayload = {
    title: `${plan.value.title} · 完整食谱`,
    meals: plan.value.days.flatMap((d) =>
      d.slots.map((s) => ({
        label: plan.value.days.length > 1 ? `${d.weekday} ${s.label}` : s.label,
        time: s.time,
        kcal: s.kcal,
        dishes: s.dishes
      }))
    )
  }
  ui.recipeOpen = true
}

function onAction(a) {
  if (a.phrase === 'reload') load()
  else send(a.phrase)
}

onMounted(load)
watch(() => panel.revision, load)
watch(() => panel.active, (v) => v === 'current_plan' && load())
</script>

<style scoped>
.sk-wrap {
  padding-top: 8px;
}

.cp-swap {
  display: block;
  margin-top: 4px;
  margin-left: auto;
  padding: 0;
  background: none;
  border: none;
  font-size: 11.5px;
  color: var(--brand-hover);
  cursor: pointer;
}

.cp-swap:hover:not(:disabled) {
  text-decoration: underline;
}

.cp-swap:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.cp-report-link {
  display: block;
  margin-top: 10px;
  padding: 0;
  background: none;
  border: none;
  font-size: 12.5px;
  color: var(--brand-hover);
  cursor: pointer;
  text-align: left;
}

.cp-report-link:hover {
  text-decoration: underline;
}

.cp-report-link:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* 方案级「营养提示」：跨日微量补足建议（为什么这么搭归对话 explain，不在面板重复） */
.plan-nutrition {
  margin: 10px 0 14px;
  padding: 10px 12px;
  background: var(--bg-soft, #fafafa);
  border-radius: 10px;
}

.plan-nutrition-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-main, #333);
  margin-bottom: 6px;
}

.plan-nutrition-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-sub, #7a7a7a);
}

.plan-nutrition-list li {
  margin: 2px 0;
}

/* 数据说明：中性脚注，默认折叠，与上方「营养提示」分开，不放人话依据里 */
.plan-data-notes {
  margin: 0 0 14px;
  padding: 8px 12px;
  background: var(--bg-soft, #fafafa);
  border-radius: 10px;
}

.pdn-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-sub, #7a7a7a);
  text-align: left;
}

.pdn-count {
  font-size: 11px;
  color: var(--text-sub, #9a9a9a);
}

.pdn-chevron {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-sub, #9a9a9a);
}

.pdn-list {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-sub, #7a7a7a);
}

.pdn-list li {
  margin: 2px 0;
}
</style>
