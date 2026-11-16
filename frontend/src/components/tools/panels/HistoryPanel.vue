<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 70%"></div>
      <div class="skeleton sk-line" style="width: 50%"></div>
      <div class="skeleton sk-line" style="width: 62%"></div>
    </div>

    <template v-else-if="groups.length">
      <div class="report-archive-section-title">共 {{ total }} 份方案</div>

      <template v-for="g in groups" :key="g.label">
        <div class="history-group-label">{{ g.label }}</div>
        <div v-for="p in g.items" :key="p.plan_id" class="history-plan" @click="view(p)">
          <div style="min-width: 0">
            <div class="plan-title">{{ p.title }}</div>
            <div class="plan-range">
              {{ p.range_text }}<span v-if="p.created_text"> · {{ p.created_text }}</span>
              <span v-if="p.status !== 'fixed'" class="pending-tag">{{ p.status_label }}</span>
            </div>
          </div>
          <label class="plan-action-row" @click.stop>
            <input type="checkbox" :checked="p.is_executed" @change="toggleExecuted(p, $event)" />
            <div class="plan-checkbox"></div>
            <span class="plan-status-text">{{ p.is_executed ? '已执行' : '未执行' }}</span>
          </label>
        </div>
      </template>

      <div v-if="total > plans.length" class="panel-note">
        已显示 {{ plans.length }}/{{ total }} 份，回到面板顶部可重新加载。
      </div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="🗂️"
        title="还没有历史方案"
        desc="确认过的配餐方案会按周归档在这里，
方便你回看当时怎么吃的、有没有照做。"
        :actions="[{ icon: '🥗', label: '生成一日三餐', desc: '先让智能体为你配餐', phrase: '生成一日三餐' }]"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchPlanList, fetchPlanById, setPlanExecuted } from '@/api/mealPlan.js'
import { normalizeMealCard, STATUS_LABELS, goalLabel } from '@/utils/schema.js'
import { fmtDate, fmtDateTime } from '@/utils/format.js'
import { usePanelStore } from '@/stores/panel.js'
import { useChatStore } from '@/stores/chat.js'
import { useUi } from '@/composables/useUi.js'
import EmptyState from '@/components/common/EmptyState.vue'

const panel = usePanelStore()
const chat = useChatStore()
const ui = useUi()

const loading = ref(false)
const error = ref('')
const plans = ref([])
const total = ref(0)

const TYPE_SUFFIX = { 餐: '一餐', 日: '三餐', 多日: '方案', 周: '方案', 自定义: '方案' }

function shortRange(start, end) {
  if (!start) return ''
  if (!end || start === end) return fmtDate(start)
  return `${fmtDate(start)} - ${fmtDate(end)}`
}

function buildTitle(item) {
  const range = shortRange(item.start_date, item.end_date)
  const goal = goalLabel(item.goal_code)
  const suffix = TYPE_SUFFIX[item.plan_type] || '方案'
  return [range, goal, suffix].filter(Boolean).join(' ')
}

function weekBucket(iso) {
  if (!iso) return '更早'
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return '更早'
  const monday = (x) => {
    const t = new Date(x)
    const wd = (t.getDay() + 6) % 7
    t.setDate(t.getDate() - wd)
    t.setHours(0, 0, 0, 0)
    return t
  }
  const thisWeek = monday(new Date())
  const lastWeek = new Date(thisWeek)
  lastWeek.setDate(lastWeek.getDate() - 7)
  const d0 = new Date(d)
  d0.setHours(0, 0, 0, 0)
  if (d0 >= thisWeek) return '本周'
  if (d0 >= lastWeek) return '上周'
  return '更早'
}

function summaryView(item) {
  return {
    plan_id: item.meal_plan_id,
    plan_type: item.plan_type,
    title: buildTitle(item),
    range_text: item.start_date && item.end_date ? `${item.start_date} ~ ${item.end_date}` : '—',
    start_date: item.start_date,
    end_date: item.end_date,
    status: item.status || 'draft',
    status_label: STATUS_LABELS[item.status] || '草稿',
    is_executed: Boolean(item.is_executed),
    goal_code: item.goal_code || '',
    created_text: item.created_at ? fmtDateTime(item.created_at) : '—',
    week_bucket: weekBucket(item.start_date)
  }
}

const groups = computed(() => {
  const order = ['本周', '上周', '更早']
  const map = new Map()
  for (const p of plans.value) {
    if (!map.has(p.week_bucket)) map.set(p.week_bucket, [])
    map.get(p.week_bucket).push(p)
  }
  return order.filter((b) => map.has(b)).map((b) => ({ label: b, items: map.get(b) }))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await fetchPlanList({ page: 1, pageSize: 20 })
    plans.value = (page.items || []).map(summaryView)
    total.value = page.total || plans.value.length
  } catch (e) {
    error.value = e.message || '历史方案加载失败'
    plans.value = []
  } finally {
    loading.value = false
  }
}

async function toggleExecuted(p, event) {
  const checked = event.target.checked
  const prev = p.is_executed
  p.is_executed = checked
  try {
    await setPlanExecuted(p.plan_id, checked)
    ElMessage.success(checked ? '已标记为已执行' : '已取消执行标记')
  } catch (e) {
    p.is_executed = prev
    ElMessage.error(e.message || '标记失败')
  }
}

async function view(p) {
  try {
    const raw = await fetchPlanById(p.plan_id)
    if (!raw) {
      ElMessage('这份方案已经找不到了')
      return
    }
    const plan = normalizeMealCard(raw)
    ui.historyPayload = {
      plan_id: p.plan_id,
      title: p.title,
      range_text: p.range_text,
      goal_label: goalLabel(raw.goal_code || p.goal_code),
      status_label: p.status_label,
      is_executed: Boolean(raw.is_executed),
      days: plan.days
    }
    ui.historyOpen = true
  } catch (e) {
    ElMessage.error(e.message || '打开方案失败')
  }
}

function onAction(a) {
  if (a.phrase === 'reload') load()
  else chat.send(a.phrase)
}

onMounted(load)
watch(() => panel.revision, load)
watch(() => panel.active, (v) => v === 'history' && load())
</script>

<style scoped>
.sk-wrap {
  padding-top: 8px;
}

.history-group-label {
  font-size: 11px;
  color: var(--text-sub);
  margin: 16px 2px 8px;
  font-weight: 500;
  letter-spacing: 0.05em;
}

.history-group-label:first-of-type {
  margin-top: 4px;
}

.pending-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 5px;
  font-size: 11px;
  color: var(--brand-hover);
  background: var(--brand-light, #eef4f0);
  border-radius: 4px;
}
</style>
