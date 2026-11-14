<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 70%"></div>
      <div class="skeleton sk-line" style="width: 50%"></div>
      <div class="skeleton sk-line" style="width: 62%"></div>
    </div>

    <template v-else-if="plans.length">
      <div class="report-archive-section-title">共 {{ total }} 份方案</div>

      <div v-for="p in plans" :key="p.plan_id" class="history-plan" @click="view(p)">
        <div style="min-width: 0">
          <div class="plan-title">{{ p.title }}</div>
          <div class="plan-range">{{ p.range_text }} · {{ p.created_text }}</div>
        </div>
        <span class="type-tag" :class="p.status === 'fixed' ? 'live' : 'archive'">{{ p.status_label }}</span>
      </div>

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
        desc="生成过的配餐方案会归档在这里，
方便你回看当时怎么吃的。"
        :actions="[{ icon: '🥗', label: '生成一日三餐', desc: '先让智能体为你配餐', phrase: '生成一日三餐' }]"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchPlanList, fetchPlanById } from '@/api/mealPlan.js'
import { normalizeMealCard, planTypeTitle, STATUS_LABELS } from '@/utils/schema.js'
import { fmtDateTime } from '@/utils/format.js'
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

function summaryView(item) {
  return {
    plan_id: item.meal_plan_id,
    plan_type: item.plan_type,
    title: planTypeTitle(item.plan_type),
    range_text:
      item.start_date && item.end_date ? `${item.start_date} ~ ${item.end_date}` : '—',
    status: item.status || 'draft',
    status_label: STATUS_LABELS[item.status] || '草稿',
    created_text: item.created_at ? fmtDateTime(item.created_at) : '—',
    goal_energy_kcal: item.goal_energy_kcal
  }
}

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

async function view(p) {
  try {
    const raw = await fetchPlanById(p.plan_id)
    if (!raw) {
      ElMessage('这份方案已经找不到了')
      return
    }
    const plan = normalizeMealCard(raw)
    ui.recipePayload = {
      title: `${planTypeTitle(plan.plan_type)} · ${plan.range_text}`.trim(),
      meals: plan.days.flatMap((d) =>
        d.slots.map((s) => ({ label: `${dayLabel(d)} ${s.label}`, time: s.time, kcal: s.kcal, dishes: s.dishes }))
      )
    }
    ui.recipeOpen = true
  } catch (e) {
    ElMessage.error(e.message || '打开方案失败')
  }
}

function dayLabel(d) {
  return d.is_today ? '今天' : d.weekday || d.date
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
</style>
