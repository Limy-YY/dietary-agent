<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 70%"></div>
      <div class="skeleton sk-line" style="width: 50%"></div>
      <div class="skeleton sk-line" style="width: 62%"></div>
    </div>

    <template v-else-if="plans.length">
      <div class="report-archive-section-title">共 {{ plans.length }} 份方案</div>

      <div v-for="p in plans" :key="p.plan_id" class="history-plan" @click="view(p)">
        <div style="min-width: 0">
          <div class="plan-title">{{ p.title }}</div>
          <div class="plan-range">{{ p.range_text }}</div>
        </div>
        <label class="plan-action-row" @click.stop>
          <input type="checkbox" :checked="executedMap[p.plan_id]" @change="toggleExecuted(p, $event.target.checked)" />
          <div class="plan-checkbox"></div>
          <span class="plan-status-text">{{ executedMap[p.plan_id] ? '已执行' : '未执行' }}</span>
        </label>
      </div>

      <div class="panel-note">勾选可以标记这份方案是否已经执行过。</div>
    </template>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else>
      <EmptyState
        icon="🗂️"
        title="还没有历史方案"
        desc="确认过的配餐方案会按周归档在这里，
方便你回看当时怎么吃的。"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchPlanList, fetchPlanById } from '@/api/mealPlan.js'
import { normalizePlan } from '@/utils/schema.js'
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
const executedMap = reactive({})
const updatedText = computed(() => (plans.value[0]?.created_at ? fmtDateTime(plans.value[0].created_at) : '—'))

function toggleExecuted(p, checked) {
  executedMap[p.plan_id] = checked
  ElMessage(checked ? '已标记为已执行' : '已取消执行标记')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    plans.value = await fetchPlanList()
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
    const plan = normalizePlan(raw)
    ui.recipePayload = {
      title: `${plan.title} · ${plan.range_text || ''}`.trim(),
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
