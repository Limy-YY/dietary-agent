<template>
  <div>
    <div v-if="loading" class="sk-wrap">
      <div class="skeleton sk-line" style="width: 65%"></div>
      <div class="skeleton sk-line" style="width: 50%"></div>
      <div class="skeleton sk-line" style="width: 62%"></div>
    </div>

    <template v-else-if="error">
      <EmptyState icon="⚠️" title="加载失败" :desc="error" :actions="[{ label: '重新加载', phrase: 'reload' }]" @action="onAction" />
    </template>

    <template v-else-if="items.length">
      <div class="report-archive-section-title">已生成的报告（{{ total }}）</div>
      <div v-for="r in items" :key="r.id" class="report-archive-item" @click="open(r)">
        <div class="ra-title">
          {{ r.title }}<span class="ra-badge">{{ r.badge }}</span>
        </div>
        <div class="ra-meta">{{ r.range }} · {{ r.generated }}</div>
      </div>
      <div class="es-hint" style="margin-top: 16px">
        💡 想生成新报告？在底部输入框说<br />
        <b>「生成周膳食报告」</b> 或 <b>「生成月膳食报告」</b>
      </div>
    </template>

    <template v-else>
      <EmptyState
        icon="📄"
        title="暂未生成膳食报告"
        desc="报告会复盘宏量供能比、7 项关键微量与每日热量趋势；已固定的方案越多越有参考价值。"
        :actions="[
          { icon: '🥗', label: '生成一日三餐', desc: '先让智能体为你配餐', phrase: '生成一日三餐' },
          { icon: '📊', label: '生成周膳食报告', desc: '复盘近 7 天已固定方案', phrase: '生成周膳食报告' }
        ]"
        hint="💡 也可以说：<br /><b>「生成月膳食报告」</b> 复盘近 30 天。"
        @action="onAction"
      />
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchReportList, fetchReportById } from '@/api/nutrition.js'
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
const items = ref([])
const total = ref(0)

const TYPE_TITLE = { week: '周膳食报告', month: '月膳食报告', custom: '自定义膳食报告' }
const TYPE_BADGE = { week: '周', month: '月', custom: '自定义' }

function summaryView(item) {
  return {
    id: item.nutrition_report_id,
    title: TYPE_TITLE[item.report_type] || '膳食报告',
    badge: TYPE_BADGE[item.report_type] || String(item.report_type || ''),
    range:
      item.period_start && item.period_end ? `${item.period_start} ~ ${item.period_end}` : '—',
    generated: item.generated_at ? fmtDateTime(item.generated_at) : '—'
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await fetchReportList({ page: 1, pageSize: 50 })
    items.value = (page.items || []).map(summaryView)
    total.value = page.total || items.value.length
  } catch (e) {
    error.value = e.message || '报告列表加载失败'
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function open(item) {
  try {
    const raw = await fetchReportById(item.id)
    if (!raw) {
      ElMessage('这份报告已经找不到了')
      return
    }
    ui.reportPayload = raw
    ui.reportOpen = true
  } catch (e) {
    ElMessage.error(e.message || '报告加载失败')
  }
}

function onAction(a) {
  if (a.phrase === 'reload') load()
  else chat.send(a.phrase)
}

onMounted(load)
watch(() => panel.revision, load)
watch(() => panel.active, (v) => v === 'report' && load())
</script>

<style scoped>
.sk-wrap {
  padding-top: 8px;
}
</style>
